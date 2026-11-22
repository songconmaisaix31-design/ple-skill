#!/usr/bin/env bash
# PLE-Bench harness: cloud / Linux host runbook (kit check + 29-task dev set).
#
# 文件名沿用 wsl-run.sh，但已泛化：**任意能跑 Docker daemon 的 Linux 主机**都能用，
# 不再依赖 WSL2，也不依赖 /mnt/c。官方链路必须跑在 Linux 文件系统里（eval/README.md）。
# 首次上云先跑：bash devtools/cloud-preflight.sh
#
#   bash devtools/wsl-run.sh env      # 生成 ~/ple-work/local.env 模板
#   bash devtools/wsl-run.sh gcp      # 仅 A 档：gcloud ADC 登录（浏览器交互，本人操作）
#   bash devtools/wsl-run.sh hf       # 验证 HF gated 授权
#   bash devtools/wsl-run.sh proxy    # 起模型代理并自检 /health 与 /v1/messages
#   bash devtools/wsl-run.sh check    # kit check --no-smoke --cancel-test
#   bash devtools/wsl-run.sh dev      # 1~2 题真模型验证 + 全量 29 题 dev set
#   bash devtools/wsl-run.sh ready    # artifacts 校验 + 全量 kit check
#
# 模型通道（HANDOFF.md §11.2）：
#   PLE_PROXY_BACKEND=vertex      A 档：官方 kit/model_proxy/start.sh → Vertex AI
#                                 需 VERTEXAI_PROJECT + gcloud ADC + 结算
#   PLE_PROXY_BACKEND=selfhosted  B 档：自有云端 API key 经 LiteLLM
#                                 需 PLE_PROXY_CONFIG 指向 litellm 配置 + 云端 key
# **两种通道都不改 submission.yaml 的 model_api（必须保持 google-cloud/claude-opus-5-5）**
#
# 可覆盖的环境变量：
#   PLE_ROOT / PLE_ENTRY_URL / PLE_KIT_URL / PLE_ENTRY_LOCAL / PLE_KIT_LOCAL
#   PLE_WIN_ENTRY      Windows 侧仓库路径，仅用于把 artifacts 拷回（不设则跳过）
#   PLE_PROXY_PORT    代理端口（默认 4000）
#   PLE_PROXY_BACKEND vertex | selfhosted（默认 vertex）
#   PLE_PROXY_CONFIG  B 档 litellm 配置文件路径
#   PLE_SMOKE_TASKS   dev 阶段先跑的题（逗号分隔）；置空可跳过
set -euo pipefail

ROOT="${PLE_ROOT:-$HOME/ple-work}"
ENTRY="$ROOT/ple-skill"
KIT="$ROOT/ple-official"
ENTRY_URL="${PLE_ENTRY_URL:-https://github.com/songconmaisaix31-design/ple-skill.git}"
KIT_URL="${PLE_KIT_URL:-https://github.com/google-research/ple.git}"
WIN_ENTRY="${PLE_WIN_ENTRY:-}"
ENVFILE="$ROOT/local.env"
PROXY_PORT="${PLE_PROXY_PORT:-4000}"
PROXY_BACKEND="${PLE_PROXY_BACKEND:-vertex}"
PROXY_CONFIG="${PLE_PROXY_CONFIG:-$ROOT/litellm.yaml}"
SMOKE_TASKS="${PLE_SMOKE_TASKS-data-center-site-model,engineers-estimate-check}"
STAGE="${1:-check}"

log() { printf '\n=== %s ===\n' "$*"; }

load_env() {
  [[ -f "$ENVFILE" ]] || { echo "缺少 $ENVFILE，先跑：bash $0 env"; exit 1; }
  set -a; . "$ENVFILE"; set +a
  # 占位符用纯字母，避免 shell 把 <...> 当重定向
  if [[ "$PROXY_BACKEND" == "vertex" ]]; then
    [[ "${VERTEXAI_PROJECT:-}" != REPLACE_WITH_* ]] || { echo "A 档需先在 $ENVFILE 填 VERTEXAI_PROJECT（或改用 PLE_PROXY_BACKEND=selfhosted）"; exit 1; }
  fi
}

make_env() {
  log "生成 $ENVFILE（已存在则绝不覆盖）"
  mkdir -p "$ROOT"
  if [[ -f "$ENVFILE" ]]; then
    echo "已存在，保留：$ENVFILE"
  else
    umask 077
    cat > "$ENVFILE" <<EOF
# 只放在 ~/ple-work/，绝不要放进参赛仓库。权限 600。
HF_TOKEN=REPLACE_WITH_HF_READ_TOKEN
MODEL_PROXY_KEY=$(openssl rand -hex 24)
MODEL_PROXY_URL=http://localhost:$PROXY_PORT

# A 档（PLE_PROXY_BACKEND=vertex，官方 Vertex AI 通道）
VERTEXAI_PROJECT=REPLACE_WITH_GCP_PROJECT

# B 档（PLE_PROXY_BACKEND=selfhosted，自有云端 API key 经 LiteLLM）
# 用哪档就填哪项，另一档可留占位；submission.yaml 的 model_api 始终不改。
# ANTHROPIC_API_KEY=REPLACE_WITH_YOUR_CLOUD_KEY
EOF
    echo "已创建：$ENVFILE（权限 600）"
  fi
  echo "请填 HF_TOKEN，并按所选通道填 VERTEXAI_PROJECT 或 ANTHROPIC_API_KEY。"
  echo "B 档还需：cp devtools/litellm-selfhosted.yaml.example $PROXY_CONFIG"
}

setup_gcp() {
  log "A 档：GCP / gcloud ADC（B 档不需要这一步）"
  if ! command -v gcloud >/dev/null; then
    echo "没装 gcloud，先执行："
    echo "  curl -sSL https://sdk.cloud.google.com | bash"
    echo "  exec -l \$SHELL   # 重开 shell 让 gcloud 进 PATH"
    exit 1
  fi
  load_env
  echo "project: $VERTEXAI_PROJECT"
  echo "接下来会打开浏览器做 gcloud auth application-default login，请本人完成登录。"
  gcloud auth application-default login
  gcloud config set project "$VERTEXAI_PROJECT"
}

start_proxy() {
  load_env
  : "${MODEL_PROXY_KEY:?在 $ENVFILE 里填 MODEL_PROXY_KEY}"
  if curl -fsS --max-time 2 "http://127.0.0.1:$PROXY_PORT/health/liveliness" >/dev/null 2>&1; then
    echo "model_proxy 已在 :$PROXY_PORT 运行，复用"
  else
    case "$PROXY_BACKEND" in
      vertex)
        : "${VERTEXAI_PROJECT:?A 档需 VERTEXAI_PROJECT}"
        log "A 档：启动官方 model_proxy（Vertex AI，费用记在 $VERTEXAI_PROJECT）"
        (cd "$KIT" && MODEL_PROXY_HOST=0.0.0.0 MODEL_PROXY_PORT="$PROXY_PORT" \
            VERTEXAI_PROJECT="$VERTEXAI_PROJECT" MODEL_PROXY_KEY="$MODEL_PROXY_KEY" \
            nohup kit/model_proxy/start.sh > "$ROOT/model_proxy.log" 2>&1 &)
        ;;
      selfhosted)
        [[ -f "$PROXY_CONFIG" ]] || { echo "B 档缺少代理配置：$PROXY_CONFIG（从 devtools/litellm-selfhosted.yaml.example 复制）"; exit 1; }
        log "B 档：启动 LiteLLM 代理（自有云端 key，配置 $PROXY_CONFIG）"
        (MODEL_PROXY_KEY="$MODEL_PROXY_KEY" nohup uv run --no-project --python 3.11 \
            --with 'litellm[proxy]==1.90.0' litellm \
            --config "$PROXY_CONFIG" --host 0.0.0.0 --port "$PROXY_PORT" \
            > "$ROOT/model_proxy.log" 2>&1 &)
        ;;
      *) echo "PLE_PROXY_BACKEND 只能是 vertex 或 selfhosted"; exit 2 ;;
    esac
    for _ in $(seq 1 60); do
      curl -fsS --max-time 2 "http://127.0.0.1:$PROXY_PORT/health/liveliness" >/dev/null 2>&1 && break
      sleep 2
    done
    curl -fsS --max-time 3 "http://127.0.0.1:$PROXY_PORT/health/liveliness" >/dev/null \
      || { echo "proxy 未就绪，看 $ROOT/model_proxy.log"; exit 1; }
  fi
  export MODEL_PROXY_URL="http://localhost:$PROXY_PORT"
  echo "MODEL_PROXY_URL=$MODEL_PROXY_URL（proxy 必须 bind 0.0.0.0，Docker bridge 才能连到）"
}

probe_proxy() {
  log "代理协议自检（harness 走 Anthropic Messages 原生路径）"
  local code
  code=$(curl -sS -o /tmp/ple_proxy_probe.out -w '%{http_code}' --max-time 60 \
      -H "Authorization: Bearer $MODEL_PROXY_KEY" \
      -H 'content-type: application/json' -H 'anthropic-version: 2023-06-01' \
      -d '{"model":"claude-opus-5-5","max_tokens":16,"messages":[{"role":"user","content":"ping"}]}' \
      "http://127.0.0.1:$PROXY_PORT/v1/messages" || echo 000)
  echo "POST /v1/messages → HTTP $code"
  head -c 240 /tmp/ple_proxy_probe.out 2>/dev/null; echo
  if [[ "$code" != "200" ]]; then
    echo "原生端点不可用：换支持 /v1/messages 的网关，或改 skillkit/model.py 走 OpenAI 兼容分支"
    echo "（改代码后必须重跑 protocol_smoke.py + 全量 kit check + 全量 dev set）"
    exit 1
  fi
  echo "再确认 judge 模型名可用：把上面 body 的 model 换成 claude-opus-5-5-judge 重试一次"
}

check_hf() {
  load_env
  : "${HF_TOKEN:?dev set 需要 HF_TOKEN：数据集页申请 access 后创建 read token}"
  [[ "$HF_TOKEN" != REPLACE_WITH_* ]] || { echo "先在 $ENVFILE 填 HF_TOKEN"; exit 1; }
  log "验证 HF gated 授权（200 = 已授权，401/403 = 还没通过）"
  local code
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 \
      -H "Authorization: Bearer $HF_TOKEN" \
      "https://huggingface.co/api/datasets/google/physical-engineerings-last-exam" || echo 000)
  echo "HTTP $code"
  [[ "$code" == "200" ]] || {
    echo "gated 授权未生效或网络不通。检查："
    echo "  1) 数据集页已登录并点过 Agree and access"
    echo "  2) huggingface.co 可达"
    echo "  3) 退路：预先下载任务目录，用 eval/run.py --tasks-dir DIR"
    exit 1
  }
}

preflight() {
  log "0. 前置检查（详细探测请用 devtools/cloud-preflight.sh）"
  local missing=0
  for c in docker git uv python3 curl openssl; do
    if ! command -v "$c" >/dev/null; then echo "缺少 $c"; missing=1; fi
  done
  (( missing == 0 )) || exit 1
  docker info >/dev/null 2>&1 || { echo "Docker daemon 未就绪，先装 dockerd / 启动 Docker Desktop"; exit 1; }
  local mem
  mem=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
  if (( mem < 16 * 1024 * 1024 * 1024 )); then
    echo "警告：Docker 内存 $((mem / 1024 / 1024 / 1024)) GiB < 16 GiB，全量 dev set 可能 OOM"
    echo "      云主机选 >=16.25 GiB 机型；Docker Desktop 在 Settings > Resources 调大"
  fi
  [[ -f "$ENVFILE" ]] || { echo "缺少 $ENVFILE，先跑：bash $0 env"; exit 1; }
  case "$(uname -s)" in
    Linux) : ;;
    *) echo "官方 kit 必须在 Linux 上运行（kit/build.py 依赖 fcntl）"; exit 1 ;;
  esac
}

clone_or_local() {
  local dest="$1" url="$2" local="${3:-}"
  if [[ -d "$dest/.git" ]]; then
    echo "已存在 $dest，保留现状（不会覆盖本地 artifacts）"
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  if [[ -n "$local" && -d "$local/.git" ]]; then
    echo "从本地克隆：$local → $dest"
    git clone "$local" "$dest"
  else
    echo "从 GitHub 克隆：$url → $dest"
    git clone "$url" "$dest"
  fi
}

sync_repos() {
  log "1. 仓库落到 Linux 文件系统（~/，不是 /mnt/c；避免 symlink / CRLF 坑）"
  clone_or_local "$ENTRY" "$ENTRY_URL" "${PLE_ENTRY_LOCAL:-}"
  clone_or_local "$KIT"  "$KIT_URL"  "${PLE_KIT_LOCAL:-}"
  git -C "$ENTRY" config core.filemode true
  git -C "$ENTRY" config core.symlinks true
  git -C "$ENTRY" config core.autocrlf input
  git -C "$ENTRY" config user.name "ple-skill handoff"
  git -C "$ENTRY" config user.email "handoff@local"
  echo "entry git status:"; git -C "$ENTRY" status --porcelain
  echo "entry file modes:"; git -C "$ENTRY" ls-tree HEAD serve.py dryrun.py
}

install_tools() {
  log "2. 安装 Harbor 0.20.0 与 kit 依赖"
  uv tool install harbor==0.20.0 --with websockets
  (cd "$KIT" && uv sync -q)
}

sync_back_artifacts() {
  if [[ -n "$WIN_ENTRY" && -d "$WIN_ENTRY" ]]; then
    cp -a "$ENTRY/artifacts" "$WIN_ENTRY/"
    echo "已复制 artifacts → $WIN_ENTRY/artifacts"
  else
    echo "未设置/未找到 Windows 侧仓库，跳过拷贝；artifacts 仍在 $ENTRY/artifacts"
  fi
}

case "$STAGE" in
  env)    make_env ;;
  gcp)    setup_gcp ;;
  hf)     check_hf ;;
  proxy)  load_env; start_proxy; probe_proxy ;;
  check)
    preflight; sync_repos; install_tools; start_proxy
    log "3. kit check（先跳过 smoke，打掉 build / listen / cancel 这类判 0 门槛）"
    (cd "$KIT" && uv run python -m kit check "$ENTRY" \
        --env-file "$ENVFILE" --no-smoke --cancel-test)
    log "4. 通过后跑全量检查（--no-smoke 不会打印 ready to submit）"
    echo "  cd $KIT && uv run python -m kit check $ENTRY --env-file $ENVFILE"
    ;;
  dev)
    preflight; check_hf; sync_repos; install_tools; start_proxy
    if [[ -n "$SMOKE_TASKS" ]]; then
      log "3. 先用 1~2 题验真模型与 Anthropic 路径"
      (cd "$KIT" && uv run python eval/run.py "$ENTRY" --env-file "$ENVFILE" \
          --tasks "$SMOKE_TASKS" --trials 1)
      echo "  看 runs/<run>/attempt1/harbor.log，确认无 400 / tool_use 序列化异常"
    fi
    log "4. 全量 29 题 dev set（写出 \$ENTRY/artifacts/）"
    (cd "$KIT" && uv run python eval/run.py "$ENTRY" --env-file "$ENVFILE")
    log "5. 把 artifacts 拷回 Windows 仓库（可选）"
    sync_back_artifacts
    echo "  重要：在 ENTRY 里 git add artifacts && git commit && git push，与代码同一个 commit（F-02）"
    ;;
  ready)
    preflight; sync_repos; install_tools; start_proxy
    log "3. 产物校验 + 离线重判 + readiness"
    (cd "$KIT" && uv run python -m kit artifacts "$ENTRY")
    (cd "$KIT" && uv run python eval/run.py --artifacts "$ENTRY" --env-file "$ENVFILE")
    (cd "$KIT" && uv run python -m kit check "$ENTRY" --env-file "$ENVFILE")
    echo "  末行必须是 ready to submit；然后把代码与 artifacts 一起提交并推送"
    ;;
  *)
    echo "用法: $0 {env|gcp|hf|proxy|check|dev|ready}"; exit 2 ;;
esac
