#!/usr/bin/env bash
# PLE-Bench harness: kit check + 29-task dev set inside WSL2.
#
# 必须在 WSL2 的 Linux 文件系统里跑（~/，不是 /mnt/c）；用 WSL 自带的 git/uv/python。
#   bash devtools/wsl-run.sh env      # 生成 ~/ple-work/local.env 模板（填两个占位）
#   bash devtools/wsl-run.sh gcp      # gcloud ADC 登录（浏览器交互，本人操作）
#   bash devtools/wsl-run.sh hf       # 验证 HF gated 授权
#   bash devtools/wsl-run.sh check    # kit check --no-smoke --cancel-test
#   bash devtools/wsl-run.sh dev      # 1~2 题真模型验证 + 全量 29 题 dev set
#   bash devtools/wsl-run.sh ready    # artifacts 校验 + 全量 kit check
#
# 可覆盖的环境变量：
#   PLE_ROOT         工作根目录（默认 ~/ple-work）
#   PLE_ENTRY_URL    参赛仓库 URL（默认本仓库）
#   PLE_KIT_URL      官方 kit URL
#   PLE_ENTRY_LOCAL  本地参赛仓库路径（离线时优先于 URL）
#   PLE_KIT_LOCAL    本地官方 kit 路径（离线时优先于 URL）
#   PLE_WIN_ENTRY    Windows 侧仓库路径，仅用于把 artifacts 拷回（不存在就跳过）
#   PLE_SMOKE_TASKS  dev 阶段先跑的题（逗号分隔）；置空可跳过
#
# 前置：Docker Desktop（WSL2 integration 打开、内存 >= 16.25 GiB）、
#       HF_TOKEN（已在数据集页 Agree and access）、
#       GCP project 启用 Vertex AI 并绑定结算账号。
set -euo pipefail

ROOT="${PLE_ROOT:-$HOME/ple-work}"
ENTRY="$ROOT/ple-skill"
KIT="$ROOT/ple-official"
ENTRY_URL="${PLE_ENTRY_URL:-https://github.com/songconmaisaix31-design/ple-skill.git}"
KIT_URL="${PLE_KIT_URL:-https://github.com/google-research/ple.git}"
WIN_ENTRY="${PLE_WIN_ENTRY:-/mnt/c/Users/DW/WorkBuddy/2026-11-22-23-52-42/ple-skill}"
ENVFILE="$ROOT/local.env"
PROXY_PORT="${PLE_PROXY_PORT:-4000}"
SMOKE_TASKS="${PLE_SMOKE_TASKS-data-center-site-model,engineers-estimate-check}"
STAGE="${1:-check}"

log() { printf '\n=== %s ===\n' "$*"; }

load_env() {
  [[ -f "$ENVFILE" ]] || { echo "缺少 $ENVFILE，先跑：bash $0 env"; exit 1; }
  set -a; . "$ENVFILE"; set +a
  # 占位符用纯字母，避免 shell 把 <...> 当重定向
  [[ "${VERTEXAI_PROJECT:-}" != REPLACE_WITH_* ]] || { echo "先在 $ENVFILE 填 VERTEXAI_PROJECT"; exit 1; }
}

make_env() {
  log "生成 $ENVFILE（已存在则绝不覆盖）"
  mkdir -p "$ROOT"
  if [[ -f "$ENVFILE" ]]; then
    echo "已存在，保留：$ENVFILE"
  else
    umask 077
    cat > "$ENVFILE" <<EOF
# 只放在 WSL 的 ~/ple-work/，绝不要放进参赛仓库。
VERTEXAI_PROJECT=REPLACE_WITH_GCP_PROJECT
MODEL_PROXY_KEY=$(openssl rand -hex 24)
MODEL_PROXY_URL=http://localhost:$PROXY_PORT
HF_TOKEN=REPLACE_WITH_HF_READ_TOKEN
EOF
    echo "已创建：$ENVFILE（权限 600）"
  fi
  echo "请把两个 REPLACE_WITH_... 占位替换掉，再跑 check / dev。"
}

setup_gcp() {
  log "GCP / gcloud ADC"
  if ! command -v gcloud >/dev/null; then
    echo "WSL 里没装 gcloud，先执行："
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
  : "${VERTEXAI_PROJECT:?在 $ENVFILE 里填 VERTEXAI_PROJECT}"
  : "${MODEL_PROXY_KEY:?在 $ENVFILE 里填 MODEL_PROXY_KEY}"
  if curl -fsS --max-time 2 "http://127.0.0.1:$PROXY_PORT/health/liveliness" >/dev/null 2>&1; then
    echo "model_proxy 已在 :$PROXY_PORT 运行，复用"
  else
    log "启动官方 model_proxy（Vertex AI，费用记在 $VERTEXAI_PROJECT）"
    (cd "$KIT" && MODEL_PROXY_HOST=0.0.0.0 MODEL_PROXY_PORT="$PROXY_PORT" \
        VERTEXAI_PROJECT="$VERTEXAI_PROJECT" MODEL_PROXY_KEY="$MODEL_PROXY_KEY" \
        nohup kit/model_proxy/start.sh > "$ROOT/model_proxy.log" 2>&1 &)
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
    echo "  2) huggingface.co 可达（CLI 侧曾出现代理 502 / 直连超时）"
    echo "  3) 退路：预先下载任务目录，用 eval/run.py --tasks-dir DIR"
    exit 1
  }
}

preflight() {
  log "0. 前置检查"
  local missing=0
  for c in docker git uv python3 curl openssl; do
    if ! command -v "$c" >/dev/null; then echo "缺少 $c"; missing=1; fi
  done
  (( missing == 0 )) || exit 1
  docker info >/dev/null 2>&1 || { echo "Docker daemon 未就绪，先启动 Docker Desktop 并打开 WSL2 integration"; exit 1; }
  local mem
  mem=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
  if (( mem < 16 * 1024 * 1024 * 1024 )); then
    echo "警告：Docker 内存 $((mem / 1024 / 1024 / 1024)) GiB < 16 GiB，全量 dev set 可能 OOM"
    echo "      Docker Desktop > Settings > Resources > Memory 调到 16.25 GiB 以上"
  fi
  [[ -f "$ENVFILE" ]] || { echo "缺少 $ENVFILE，先跑：bash $0 env"; exit 1; }
  [[ "$(uname -r)" == *WSL2* || "$(uname -s)" == "Linux" ]] || echo "警告：建议在 WSL2 Linux 文件系统里执行"
}

clone_or_local() {
  # $1 = target dir, $2 = url, $3 = optional local path
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
  log "1. 仓库落到 WSL2 Linux 文件系统（~/，避开 /mnt/c 的 symlink / CRLF 坑）"
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
  if [[ -d "$WIN_ENTRY" ]]; then
    cp -a "$ENTRY/artifacts" "$WIN_ENTRY/"
    echo "已复制 artifacts → $WIN_ENTRY/artifacts"
  else
    echo "未找到 Windows 侧仓库 $WIN_ENTRY，跳过拷贝；artifacts 仍在 $ENTRY/artifacts"
  fi
}

case "$STAGE" in
  env)   make_env ;;
  gcp)   setup_gcp ;;
  hf)    check_hf ;;
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
    echo "  重要：在 ENTRY 里 git add artifacts && git commit，与代码同一个 commit（F-02）"
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
    echo "用法: $0 {env|gcp|hf|check|dev|ready}"; exit 2 ;;
esac
