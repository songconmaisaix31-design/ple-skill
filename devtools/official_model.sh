# Source only after removing the dataset credential from the environment.
set -euo pipefail
python="$RUNNER_TEMP/ple-kit/.venv/bin/python"
export MODEL_PROXY_URL=http://127.0.0.1:4102 MODEL_NAME=gemma-4-26b
export PLE_CPU_STATE="$RUNNER_TEMP/ple-cpu" PLE_CPU_EVAL_GREEDY=true
MODEL_PROXY_KEY=$(openssl rand -hex 24)
export MODEL_PROXY_KEY
echo "::add-mask::$MODEL_PROXY_KEY"
bash "$GITHUB_WORKSPACE/devtools/start_cpu_model.sh" gemma26
source "$PLE_CPU_STATE/model.env"
trap 'kill "$(cat "$PLE_CPU_STATE/server.pid")" 2>/dev/null || true' EXIT
declared=$("$python" -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["model_api"])' "$RUNNER_TEMP/ple-entry/submission.yaml")
[[ "$PLE_CPU_MODEL_API" == "$declared" && "$PLE_CPU_MODEL_NAME" == "$MODEL_NAME" ]]
MODEL_BASE_URL="$MODEL_PROXY_URL/v1" MODEL_API_KEY="$MODEL_PROXY_KEY" \
    PYTHONPATH="$GITHUB_WORKSPACE" "$python" -m devtools.cloud_model_probe
gateway=$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}')
export JUDGE_BASE_URL="http://$gateway:4102/v1" JUDGE_MODEL="$MODEL_NAME" JUDGE_API_KEY="$MODEL_PROXY_KEY"
