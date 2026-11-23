#!/usr/bin/env bash
# Start a pinned public GGUF on a Linux x86-64 host without provider credentials.
set -euo pipefail

profile=${1:?usage: start_cpu_model.sh gemma26|granite}
state=${PLE_CPU_STATE:?set PLE_CPU_STATE to a scratch directory}
port=${PLE_CPU_PORT:-4102}
: "${MODEL_PROXY_KEY:?set the local model server key}"
umask 077
mkdir -p "$state/bin"

if [[ $(uname -m) != x86_64 ]]; then
  echo 'CPU model requires a Linux x86-64 runner.' >&2
  exit 1
fi

case "$profile" in
  gemma26)
    repo=unsloth/gemma-4-26B-A4B-it-GGUF
    revision=c099eb48e663fd284577b04978a94ffccb261841
    filename=gemma-4-26B-A4B-it-UD-IQ2_XXS.gguf
    digest=52f98e6fc6df62438dff8f57ac049f60b4c36acf93786b6aeeedc129acc02343
    bytes=9922480608
    model_name=gemma-4-26b
    model_api=google-cloud/gemma-4-26b
    min_memory_gib=12
    ;;
  granite)
    repo=ibm-granite/granite-4.1-3b-GGUF
    revision=ab4701481089b58a082ef63cc1cee738887293ff
    filename=granite-4.1-3b-Q4_K_M.gguf
    digest=662b0626cd58f443baea23559b469df6576a81d349649c59413b36a9fb32eb29
    bytes=2099501664
    model_name=granite-4.1-3b
    model_api=openai-compatible/granite-4.1-3b
    min_memory_gib=4
    ;;
  *) echo 'Unknown CPU model profile.' >&2; exit 1 ;;
esac

gib=$((1024 * 1024 * 1024))
model="$state/$filename"
space=$(df -P -B1 "$state" | awk 'NR==2 {print $4}')
memory=$(awk '/^MemAvailable:/ {print $2 * 1024}' /proc/meminfo)
required_space=$((4 * gib))
if [[ ! -f "$model" ]]; then required_space=$((required_space + bytes)); fi
if (( space < required_space )) || ! awk -v have="$memory" -v need="$((min_memory_gib * gib))" 'BEGIN {exit have < need}'; then
  printf '%s: insufficient host memory or free disk for this profile.\n' "$model_name" >&2
  exit 1
fi

download() {
  env -u HF_TOKEN -u HUGGING_FACE_HUB_TOKEN -u HF_OIDC_RESOURCE -u HF_OIDC_ID_TOKEN \
    -u ACTIONS_ID_TOKEN_REQUEST_URL -u ACTIONS_ID_TOKEN_REQUEST_TOKEN -u MODEL_PROXY_KEY \
    curl --fail --silent --show-error --location --http1.1 \
      --retry 20 --retry-delay 5 --retry-all-errors --continue-at - \
      --connect-timeout 20 --max-time 2700 \
      --proto '=https' --proto-redir '=https' "$1" -o "$2"
}

verify() {
  printf '%s  %s\n' "$1" "$2" | sha256sum --check --status
}

build=b12651
archive="llama-$build-bin-ubuntu-x64.tar.gz"
server="$state/bin/llama-$build/llama-server"
if [[ ! -x "$server" ]]; then
  download "https://github.com/ggml-org/llama.cpp/releases/download/$build/$archive" "$state/$archive"
  verify 17b242259181d5b1b1f7719aba27929700a8b0dab39bfaef1b971a992b397b38 "$state/$archive"
  tar -xzf "$state/$archive" -C "$state/bin"
fi

temporary="$model.partial"
trap 'rm -f "$temporary"' EXIT
if [[ ! -f "$model" ]]; then
  printf 'Downloading public %s GGUF (%s bytes).\n' "$model_name" "$bytes"
  download "https://huggingface.co/$repo/resolve/$revision/$filename?download=true" "$temporary"
  verify "$digest" "$temporary"
  mv "$temporary" "$model"
else
  verify "$digest" "$model"
fi

[[ -x "$server" ]]
key_file="$state/server-api-key"
printf '%s\n' "$MODEL_PROXY_KEY" > "$key_file"
sampling=()
if [[ "${PLE_CPU_EVAL_GREEDY:-false}" == true ]]; then
  sampling=(--temp 0 --seed 17)
fi
threads=$(nproc)
if (( threads > 4 )); then threads=4; fi

env -u HF_TOKEN -u HUGGING_FACE_HUB_TOKEN -u HF_OIDC_RESOURCE -u HF_OIDC_ID_TOKEN \
  -u ACTIONS_ID_TOKEN_REQUEST_URL -u ACTIONS_ID_TOKEN_REQUEST_TOKEN -u MODEL_PROXY_KEY \
  nohup "$server" --model "$model" --alias "$model_name" --host 0.0.0.0 --port "$port" \
    --jinja --offline --no-webui --reasoning off --api-key-file "$key_file" \
    --ctx-size 8192 --parallel 1 --threads "$threads" --threads-batch "$threads" \
    "${sampling[@]}" --gpu-layers 0 --cache-ram 0 --timeout 600 --log-disable \
    </dev/null >"$state/server.log" 2>&1 &
pid=$!
printf '%s\n' "$pid" > "$state/server.pid"
for ((attempt=0; attempt<120; attempt++)); do
  if curl --max-time 2 --fail --silent "http://127.0.0.1:$port/health" >/dev/null; then
    printf 'PLE_CPU_MODEL_NAME=%s\nPLE_CPU_MODEL_API=%s\n' "$model_name" "$model_api" > "$state/model.env"
    printf '%s model loaded with llama.cpp %s on %s CPU threads.\n' "$model_name" "$build" "$threads"
    exit 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then break; fi
  sleep 2
done
kill "$pid" 2>/dev/null || true
echo 'Local CPU model failed to become healthy.' >&2
exit 1
