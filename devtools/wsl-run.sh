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
#   bash devtools/wsl-run.sh smoke    # 运行完整 kit check，包括 smoke、MCP 与 cancel
#   bash devtools/wsl-run.sh pilot    # 默认跑 1 道自动评分题，产物仅保留在 runs/ 下
#   bash devtools/wsl-run.sh dev      # 全量 29 题 dev set，导出 artifacts/
#   bash devtools/wsl-run.sh ready    # 校验已提交的 artifacts，重判，执行完整 kit check
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
#   PLE_ENTRY_DIR     使用指定的现有参赛仓库工作区，例如正在验证的 PR checkout
#   PLE_WIN_ENTRY      Windows 侧仓库路径，仅用于把 artifacts 拷回（不设则跳过）
#   PLE_PROXY_PORT    代理端口（默认 4000）
#   PLE_PROXY_BACKEND vertex | selfhosted（默认 vertex）
#   PLE_PROXY_CONFIG  B 档 litellm 配置文件路径
#   PLE_SMOKE_TASKS   pilot 阶段跑的题（逗号分隔）
#   PLE_TASKS_DIR     已下载的官方 dev task 目录，可替代经 HF 下载任务
set -euo pipefail

ROOT="${PLE_ROOT:-$HOME/ple-work}"
[[ "$ROOT" == /* ]] || ROOT="$PWD/$ROOT"
ENTRY="${PLE_ENTRY_DIR:-$ROOT/ple-skill}"
[[ "$ENTRY" == /* ]] || ENTRY="$PWD/$ENTRY"
KIT="$ROOT/ple-official"
ENTRY_URL="${PLE_ENTRY_URL:-https://github.com/songconmaisaix31-design/ple-skill.git}"
KIT_URL="${PLE_KIT_URL:-https://github.com/google-research/ple.git}"
WIN_ENTRY="${PLE_WIN_ENTRY:-}"
ENVFILE="$ROOT/local.env"
PROXY_PORT="${PLE_PROXY_PORT:-4000}"
PROXY_BACKEND="${PLE_PROXY_BACKEND:-vertex}"
PROXY_CONFIG="${PLE_PROXY_CONFIG:-$ROOT/litellm.yaml}"
SMOKE_TASKS="${PLE_SMOKE_TASKS-wind-diaphragm-shear}"
TASKS_DIR="${PLE_TASKS_DIR:-}"
CHECK_WORK="$ROOT/kit-check"
HF_DATASET="google/physical-engineerings-last-exam"
STAGE="${1:-check}"

log() { printf '\n=== %s ===\n' "$*"; }

load_env() {
  [[ -f "$ENVFILE" ]] || { echo "缺少 $ENVFILE，先跑：bash $0 env"; exit 1; }
  local inherited_hf_token="${HF_TOKEN:-}"
  set -a; . "$ENVFILE"; set +a
  if [[ "${HF_TOKEN:-}" == REPLACE_WITH_* ]]; then
    if [[ -n "$inherited_hf_token" ]]; then
      export HF_TOKEN="$inherited_hf_token"
    else
      unset HF_TOKEN
    fi
  fi
}

require_vertex_project() {
  if [[ -z "${VERTEXAI_PROJECT:-}" || "$VERTEXAI_PROJECT" == REPLACE_WITH_* ]]; then
    echo "A 档需先在 $ENVFILE 填 VERTEXAI_PROJECT（或改用 PLE_PROXY_BACKEND=selfhosted）"
    exit 1
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
# HF_TOKEN=REPLACE_WITH_HF_READ_TOKEN  # 使用 hf auth login 时可保留注释
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
  echo "配置 Hugging Face 读取权限，并按所选通道填 VERTEXAI_PROJECT 或 ANTHROPIC_API_KEY。"
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
  require_vertex_project
  echo "project: $VERTEXAI_PROJECT"
  echo "接下来会打开浏览器做 gcloud auth application-default login，请本人完成登录。"
  gcloud auth application-default login
  gcloud config set project "$VERTEXAI_PROJECT"
}

start_proxy() {
  load_env
  : "${MODEL_PROXY_KEY:?在 $ENVFILE 里填 MODEL_PROXY_KEY}"
  export MODEL_PROXY_URL="${MODEL_PROXY_URL:-http://localhost:$PROXY_PORT}"
  local base="${MODEL_PROXY_URL%/}"
  case "${base%/v1}" in
    "http://localhost:$PROXY_PORT"|"http://127.0.0.1:$PROXY_PORT") ;;
    *) echo "使用已配置的 MODEL_PROXY_URL"; return 0 ;;
  esac
  if curl -fsS --max-time 2 "http://127.0.0.1:$PROXY_PORT/health/liveliness" >/dev/null 2>&1; then
    echo "model_proxy 已在 :$PROXY_PORT 运行，复用"
  else
    case "$PROXY_BACKEND" in
      vertex)
        require_vertex_project
        clone_or_local "$KIT" "$KIT_URL" "${PLE_KIT_LOCAL:-}"
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
  echo "MODEL_PROXY_URL=$MODEL_PROXY_URL（proxy 必须 bind 0.0.0.0，Docker bridge 才能连到）"
}

probe_proxy() {
  log "代理协议自检（harness 走 Anthropic Messages 原生路径）"
  local code base="${MODEL_PROXY_URL%/}"
  base="${base%/v1}"
  if ! code=$(printf 'Authorization: Bearer %s\n' "$MODEL_PROXY_KEY" | curl \
      -sS -o /dev/null -w '%{http_code}' --max-time 60 -H @- \
      -H 'content-type: application/json' -H 'anthropic-version: 2023-06-01' \
      -d '{"model":"claude-opus-5-5","max_tokens":16,"messages":[{"role":"user","content":"ping"}]}' \
      "$base/v1/messages"); then
    echo "无法连接配置的模型代理"
    exit 1
  fi
  echo "POST /v1/messages → HTTP $code"
  if [[ "$code" != "200" ]]; then
    echo "检查代理凭据及 claude-opus-5-5 的 Anthropic Messages 路由"
    exit 1
  fi
}

check_hf() {
  load_env
  local token="${HF_TOKEN:-${HUGGING_FACE_HUB_TOKEN:-}}" code
  if [[ -z "$token" || "$token" == REPLACE_WITH_* ]]; then
    echo "请在 $ENVFILE 填已获数据集许可的 Hugging Face read token（HF_TOKEN）"
    exit 1
  fi
  log "验证 Hugging Face 数据集读取权限"
  if ! code=$(printf 'Authorization: Bearer %s\n' "$token" | curl \
      -sS -o /dev/null -w '%{http_code}' --max-time 30 -H @- \
      "https://huggingface.co/api/datasets/$HF_DATASET/auth-check"); then
    echo "无法连接 Hugging Face，可设置 PLE_TASKS_DIR 使用已下载的官方任务目录"
    exit 1
  fi
  echo "HTTP $code"
  [[ "$code" == "200" ]] || {
    echo "gated 授权未生效或网络不通。检查："
    echo "  1) 数据集页已登录并点过 Agree and access"
    echo "  2) huggingface.co 可达"
    echo "  3) 或用 PLE_TASKS_DIR 指定已下载的官方任务目录"
    exit 1
  }
}

task_args=()
check_task_source() {
  # When no directory is supplied, the evaluator handles saved HF credentials and its cache.
  [[ -n "$TASKS_DIR" ]] || return 0
  if [[ ! -d "$TASKS_DIR" ]]; then
    echo "PLE_TASKS_DIR 不存在：$TASKS_DIR"
    exit 1
  fi
  task_args=(--tasks-dir "$(cd "$TASKS_DIR" && pwd -P)")
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
  if [[ "$STAGE" == dev || "$STAGE" == ready ]] && \
      [[ "$mem" =~ ^[0-9]+$ ]] && (( mem < 16640 * 1024 * 1024 )); then
    echo "警告：全量 dev set 最大任务及其辅助容器建议至少 16.25 GiB Docker 内存"
  fi
  [[ -f "$ENVFILE" ]] || { echo "缺少 $ENVFILE，先跑：bash $0 env"; exit 1; }
  case "$(uname -s)" in
    Linux) : ;;
    *) echo "官方 kit 必须在 Linux 上运行（kit/build.py 依赖 fcntl）"; exit 1 ;;
  esac
}

clone_or_local() {
  local dest="$1" url="$2" local="${3:-}"
  if [[ -e "$dest/.git" ]]; then
    echo "已存在 $dest，保留现状（不会覆盖本地 artifacts）"
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  if [[ -n "$local" && -e "$local/.git" ]]; then
    echo "从本地克隆：$local → $dest"
    git clone "$local" "$dest"
  else
    echo "从 GitHub 克隆：$url → $dest"
    git clone "$url" "$dest"
  fi
}

sync_repos() {
  log "1. 仓库落到 Linux 文件系统（~/，不是 /mnt/c；避免 symlink / CRLF 坑）"
  if [[ -n "${PLE_ENTRY_DIR:-}" && ( ! -e "$ENTRY/.git" || ! -f "$ENTRY/submission.yaml" ) ]]; then
    echo "PLE_ENTRY_DIR 必须指向具有 submission.yaml 的现有仓库工作区：$ENTRY"
    exit 1
  fi
  clone_or_local "$ENTRY" "$ENTRY_URL" "${PLE_ENTRY_LOCAL:-}"
  clone_or_local "$KIT"  "$KIT_URL"  "${PLE_KIT_LOCAL:-}"
  git -C "$ENTRY" config core.filemode true
  git -C "$ENTRY" config core.symlinks true
  git -C "$ENTRY" config core.autocrlf input
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

require_committed_artifacts() {
  if ! git -C "$ENTRY" cat-file -e HEAD:artifacts/manifest.json 2>/dev/null; then
    echo "提交的版本缺 artifacts/manifest.json。先运行 dev、检查产物并提交，再运行 ready。"
    exit 1
  fi
  if [[ -n "$(git -C "$ENTRY" status --porcelain)" ]]; then
    echo "工作区有未提交改动，请先核对并提交，再运行 ready。"
    exit 1
  fi
}

run_kit_check() {
  # The model and dataset settings are already exported from local.env by start_proxy.
  (cd "$KIT" && uv run python -m kit check "$ENTRY" \
      --work "$CHECK_WORK" --cancel-test "$@")
}

case "$STAGE" in
  env)    make_env ;;
  gcp)    setup_gcp ;;
  hf)     check_hf ;;
  proxy)  start_proxy; probe_proxy ;;
  check)
    preflight; sync_repos; install_tools; start_proxy
    log "3. kit check（先跳过 smoke，打掉 build / listen / cancel 这类判 0 门槛）"
    run_kit_check --no-smoke
    ;;
  smoke)
    preflight; sync_repos; install_tools; start_proxy
    log "3. 完整 kit check（含 smoke、MCP 和 cancel）"
    run_kit_check
    ;;
  pilot)
    [[ -n "$SMOKE_TASKS" ]] || { echo "请用 PLE_SMOKE_TASKS 指定至少一个公开 dev 任务"; exit 2; }
    preflight; check_task_source; sync_repos; install_tools; start_proxy
    log "3. 真模型试跑（串行，产物只保留在本次运行目录）"
    (cd "$KIT" && uv run python eval/run.py "$ENTRY" \
        --tasks "$SMOKE_TASKS" --trials 1 --attempts 1 --no-export "${task_args[@]}")
    echo "在官方评分输出的本次运行目录查看 results.json 与 attempt1/harbor.log。"
    ;;
  dev)
    preflight; check_task_source; sync_repos; install_tools; start_proxy
    log "3. 全量 29 题 dev set（写出 $ENTRY/artifacts/）"
    (cd "$KIT" && uv run python eval/run.py "$ENTRY" "${task_args[@]}")
    log "4. 把 artifacts 拷回 Windows 仓库（可选）"
    sync_back_artifacts
    echo "核对由官方评分工具生成的 artifacts，将代码与产物收入同一个 Git 快照，再运行 ready。"
    ;;
  ready)
    sync_repos; require_committed_artifacts; preflight; check_task_source; install_tools; start_proxy
    log "3. 产物校验 + 离线重判 + readiness"
    (cd "$KIT" && uv run python -m kit artifacts "$ENTRY")
    (cd "$KIT" && uv run python eval/run.py --artifacts "$ENTRY" "${task_args[@]}")
    run_kit_check
    python3 - "$CHECK_WORK/check.json" <<'PY'
import json
import sys
from pathlib import Path

report = Path(sys.argv[1])
with report.open(encoding="utf-8") as file:
    ready = json.load(file).get("ready")
if ready is not True:
    raise SystemExit(f"官方 kit 尚未确认可以提交，请检查 {report}")
PY
    ;;
  *)
    echo "用法: $0 {env|gcp|hf|proxy|check|smoke|pilot|dev|ready}"; exit 2 ;;
esac
