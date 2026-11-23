#!/usr/bin/env bash
# Read-only preflight for running the PLE dev set on a cloud Linux host.
# Does not install anything, does not write into the entry repo, does not need root.
#
#   bash devtools/cloud-preflight.sh
#
# The official runner needs a working Docker daemon and toolchain. Resource
# checks report capacity for the largest full dev task and its serve stack.
# HF and package endpoints can be unavailable when using previously cached files.
set -uo pipefail

PASS=0; WARN=0; FAIL=0
ok()   { printf '  [PASS] %s\n' "$*"; PASS=$((PASS+1)); }
warn() { printf '  [WARN] %s\n' "$*"; WARN=$((WARN+1)); }
fail() { printf '  [FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }
sec()  { printf '\n=== %s ===\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

sec "0. Host"
printf '  host  : %s\n' "$(hostname 2>/dev/null || echo unknown)"
printf '  uname : %s\n' "$(uname -srm 2>/dev/null)"
case "$(uname -s)" in
  Linux) ok "Linux host" ;;
  *)     fail "需要 Linux（Windows 直接跑不了官方 kit：kit/build.py 依赖 fcntl）" ;;
esac
case "$(uname -m)" in
  x86_64|amd64) ok "linux/amd64（kit 构建目标平台）" ;;
  *)            fail "架构 $(uname -m)：官方 kit 按 linux/amd64 构建，arm64 需确认可用" ;;
esac
if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "  环境  : WSL2（也可以，但云主机更省事）"
else
  echo "  环境  : 原生 Linux / 云主机"
fi

sec "1. Docker daemon（最关键的硬门槛）"
if ! have docker; then
  fail "没有 docker 命令。Harbor 需要真正可运行的 Docker daemon；纯沙箱 Coding Agent 通常没有"
else
  ok "docker CLI: $(docker --version 2>/dev/null | head -1)"
  if docker info >/dev/null 2>&1; then
    ok "docker daemon 可连接"
    mem=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
    cpu=$(docker info --format '{{.NCPU}}' 2>/dev/null || echo 0)
    if [[ "$mem" =~ ^[0-9]+$ ]] && (( mem > 0 )); then
      gib=$(awk -v bytes="$mem" 'BEGIN {printf "%.2f", bytes / 1073741824}')
      if (( mem >= 16640 * 1024 * 1024 )); then
        ok "Docker 内存 ${gib} GiB（覆盖官方全量 dev set 最大预留）"
      else
        warn "Docker 内存 ${gib} GiB；全量 dev set 最大任务及其辅助容器建议至少 16.25 GiB"
      fi
    else
      warn "读不到 Docker MemTotal，请手工确认 >=16.25 GiB"
    fi
    if [[ "$cpu" =~ ^[0-9]+$ ]] && (( cpu >= 6 )); then
      ok "Docker CPU ${cpu}（建议 >=6）"
    else
      warn "Docker CPU ${cpu:-?} < 6，并行度会很低"
    fi
    if timeout 90 docker run --rm hello-world >/dev/null 2>&1; then
      ok "能实际启动容器（非仅 CLI 可用）"
    else
      warn "hello-world 容器没跑起来（可能无网络拉镜像 / 无权限），需排查后再跑 eval"
    fi
  else
    fail "docker daemon 不可连接。云主机需装 dockerd；Codespaces 需启用 Docker-in-Docker"
  fi
fi

sec "2. CPU / 内存 / 磁盘"
hostcpu=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 0)
hostmem_kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
hostgib=$((hostmem_kb / 1024 / 1024))
echo "  host CPU=$hostcpu, host RAM=${hostgib} GiB"
[[ "$hostcpu" -ge 6 ]] && ok "宿主 CPU >= 6" || warn "宿主 CPU < 6"
[[ "$hostgib" -ge 16 ]] && ok "宿主 RAM >= 16 GiB" || warn "宿主 RAM < 16 GiB（容器内存才是关键，见上）"
work_path="${PLE_ROOT:-$HOME/ple-work}"
while [[ ! -d "$work_path" ]]; do work_path=$(dirname -- "$work_path"); done
freegib=$(df -PB1 -- "$work_path" 2>/dev/null | awk 'NR==2 {print int($4/1024/1024/1024)}')
if [[ -n "$freegib" ]]; then
  echo "  评分工作目录所在磁盘可用 ${freegib} GiB（$work_path）"
  [[ "$freegib" -ge 30 ]] && ok "工作目录磁盘空间充足" || warn "工作目录磁盘偏紧，请同时检查 Docker 镜像所在卷空间"
fi

sec "3. 工具链"
for c in git curl openssl python3; do
  if have "$c"; then ok "$c: $(command -v "$c")"; else fail "缺少 $c"; fi
done
if have uv; then
  ok "uv: $(uv --version 2>/dev/null)"
else
  fail "缺少 uv（官方链路必需）；安装：curl -LsSf https://astral.sh/uv/install.sh | sh"
fi
if have uv && uv tool list 2>/dev/null | grep -qi '^harbor'; then
  ok "harbor 已安装（$(uv tool list 2>/dev/null | grep -i '^harbor' | head -1)）"
else
  warn "harbor 未安装；跑：uv tool install harbor==0.20.0 --with websockets"
fi

sec "4. 出站网络（本机需要，评测容器不需要）"
probe() {
  local name="$1" url="$2" code
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$url" 2>/dev/null) || code=000
  case "$code" in
    200|301|302|401|403) ok "$name 可达（HTTP $code）" ;;
    000)                  warn "$name 暂不可达，请检查网络或已缓存的依赖与数据" ;;
    *)                    warn "$name 返回 HTTP $code，需人工确认" ;;
  esac
}
probe "huggingface.co（dev 题面，gated）" "https://huggingface.co/api/datasets/google/physical-engineerings-last-exam"
probe "github.com（匿名 clone 仓库）"     "https://github.com"
probe "pypi.org（uv 装依赖）"             "https://pypi.org/simple/"

sec "5. 凭据（只看是否设置，不打印值）"
hf_token="${HF_TOKEN:-${HUGGING_FACE_HUB_TOKEN:-}}"
if [[ -n "$hf_token" && "$hf_token" != REPLACE_WITH_* ]]; then
  ok "Hugging Face token 已设置"
  code=$(printf 'Authorization: Bearer %s\n' "$hf_token" | curl \
        -sS -o /dev/null -w '%{http_code}' --max-time 20 -H @- \
        "https://huggingface.co/api/datasets/google/physical-engineerings-last-exam/auth-check" 2>/dev/null) || code=000
  [[ "$code" == "200" ]] && ok "HF gated 授权已生效（HTTP 200）" || warn "HF gated 授权未确认（HTTP $code）；需先在数据页 Agree and access"
else
  warn "未在当前环境检测到 Hugging Face token；也可使用 CLI 登录缓存或已下载的任务目录"
fi
for k in VERTEXAI_PROJECT ANTHROPIC_API_KEY OPENAI_API_KEY MODEL_PROXY_URL MODEL_PROXY_KEY; do
  if [[ -n "${!k:-}" ]]; then echo "  $k = <set>"; else echo "  $k = <unset>"; fi
done
if [[ -z "${VERTEXAI_PROJECT:-}" && -z "${ANTHROPIC_API_KEY:-}" && -z "${OPENAI_API_KEY:-}" \
      && ( -z "${MODEL_PROXY_URL:-}" || -z "${MODEL_PROXY_KEY:-}" ) ]]; then
  warn "当前环境未检测到模型代理或凭据（也可在评分主机的 local.env 配置）"
fi

sec "6. Git 仓库卫生"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  st=$(git status --porcelain 2>/dev/null | head -5)
  [[ -z "$st" ]] && ok "工作区干净" || { warn "工作区有未提交改动："; printf '%s\n' "$st"; }
  echo "  core.autocrlf = $(git config --get core.autocrlf || echo '(unset)')"
  echo "  core.symlinks = $(git config --get core.symlinks || echo '(unset)')  <- 不能是 false"
  echo "  core.filemode = $(git config --get core.filemode || echo '(unset)')"
else
  warn "当前目录不是 git 仓库；先 clone 本仓库与 google-research/ple 到 ~/ple-work"
fi

sec "结论"
printf '  PASS=%s  WARN=%s  FAIL=%s\n' "$PASS" "$WARN" "$FAIL"
if (( FAIL > 0 )); then
  echo "  存在硬性缺项：先解决 [FAIL]，再跑 devtools/wsl-run.sh check。"
  echo "  提示：没有 Docker daemon 的纯沙箱 Coding Agent 只能改代码，eval 必须交给有 Docker 的机器。"
  exit 1
fi
echo "  硬性条件齐备。下一步："
echo "    bash devtools/wsl-run.sh env      # 填 HF_TOKEN 与模型凭据"
echo "    bash devtools/wsl-run.sh hf       # 验证 gated 授权"
echo "    bash devtools/wsl-run.sh check    # 先打掉 build/listen/cancel 门槛"
exit 0
