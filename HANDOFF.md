# PLE-Bench 参赛 harness — 剩余任务交接文档

> 交接时间：2026-11-23（GMT+8） · 交接对象：下一位接手者 / 下一轮会话
> 本文件是**当前唯一的状态基准**。`README.md` 里的「runs the dev set」与「三项指标都在 29 道真实 dev 题上量过」是上一版设计稿的措辞：**指标来自对 baseline artifacts 的离线静态回归，不是本 harness 跑过 dev set**。以本文和 `GOAL.md` 为准。

---

## 0. 30 秒接手

| 项 | 现状 |
|---|---|
| 代码 | ✅ 可编译、离线闭环自测通过、协议往返冒烟通过、已推送 GitHub |
| `kit check` | ❌ **从未跑过**（需要 WSL2 + Docker + 模型凭据） |
| 真模型端到端 | ❌ **从未跑过**（Anthropic 原生路径只做过编译级验证） |
| `artifacts/` | ❌ **目录不存在**，必须由 `eval/run.py` 生成，禁止手写 |
| dev 分数 | **0**（不是分数低，是没有产物） |
| 距截止 | 2027-01-05 23:59:59，约 43 天 |
| 当前最该做 | 解除 `wsl.exe` 黑名单 → 拿 HF / GCP 凭据 → `kit check` 打掉判 0 门槛 → 再上 dev set |

一句话：**设计完成度约 90%，工程验证完成度约 30%，提交完成度 0%。不要现在提交。**

---

## 1. 事实基线（不要凭记忆改）

| 项 | 值 | 来源 |
|---|---|---|
| 比赛 | Physical-Engineering's Last Exam (PLE-Bench)，`ple-bench.com` / `github.com/google-research/ple` | 官网 |
| Kaggle 入口 | `physical-engineerings-last-exam`；账号 **ktdkydylc 已报名**（`userHasEntered=True`） | Kaggle CLI 实测 |
| 周期 / 奖金 | 2026-11-09 → **2027-01-05 23:59:59** / 400K USD（250K / 100K / 50K） | 官网 |
| 题量 | 85 题 = 29 dev（公开）+ 56 hidden；dev 数据集 955 MB（12 checks / 14 rubric / 3 checks-judge） | 官网 / HF |
| 提交形态 | **一个 GitHub commit**：`submission.yaml` + harness + **同一 commit** 的 `artifacts/`；构建时匿名 clone 该仓库 | `docs/rules.md`、`kit/README.md` |
| 模型 | `submission.yaml` = `google-cloud/claude-opus-5-5`（8 个赞助模型之一）；本地经 `MODEL_PROXY_URL` + `MODEL_PROXY_KEY` 访问 Vertex AI | `docs/models.md` |
| 资源 | serve 容器 2 CPU / 4 GB、每题 360 分钟、3 次提交机会；**本地** Docker Desktop 建议 ≥6 CPU / **≥16.25 GiB** | `docs/protocol.md`、`eval/README.md` |
| 9 个 kit check 阶段 | submission.yaml / model-settings / files / build / model / listen / smoke / mcp / cancel / artifacts（GOAL.md 写「八个」是旧信息） | `kit/README.md` |
| 榜单参照 | Opus 5.5 原生 harness 0.483 | 官网 leaderboard |

Kaggle 只提供 `NOTE.md`（「no provided dataset」）。**dev 题面与 graders 在 HuggingFace gated dataset，不在 Kaggle**。

---

## 2. 已完成（含可复现的验证证据）

### 2.1 代码与仓库

| commit | 内容 |
|---|---|
| `17408a5` | v1 主体：spec-first harness（specgen / router / guard / transport / model / skills / dryrun / criteria） |
| `a58b197` | 5 篇 writeups |
| `084a58b` | **修复提交**（详见 `docs/01-修复与验证记录.md`） |
| `05f90e3` | 文档提交：`HANDOFF.md` / `docs/` / `devtools/` / README 状态说明（已推送） |

`084a58b` 修掉的 5 个问题：
1. `serve.py`：`ping_interval=20, ping_timeout=60` → **`ping_interval=None`**。官方 `docs/protocol.md` 明确要求关闭 keepalive（单条 `exec` 上限 600 s，长命令期间心跳会判断连、该题直接算 harness 失败）。这是原项目最高优先级的判 0 风险。
2. `guard.py` / `transport.py`：去掉硬编码 `/tmp/ple_validate.py`，改由 transport 提供 `scratch_path()` 与 `python_cmd`。评测容器仍走 `/tmp`（Linux 有 1 GB 可写），本地 dryrun 走 workdir + 当前解释器，Windows 不再炸。
3. `dryrun.py`：stub 命令改成跨平台 `python helper.py <verb>`。
4. `criteria.py`：新增 A / D / B / E 分层；缺 29 题数据时判 **BLOCKED**，不再 `0/0` 假 PASS；Docker 探测改 `shutil.which`（原来用 `bash -lc` 会误触安全策略）。
5. `.gitattributes`：源码强制 LF，默认 `-text` 保护未来 `artifacts/` 的字节哈希。git 配 `core.filemode=false` / `core.autocrlf=false` / `core.symlinks=true`；`serve.py`、`dryrun.py` 保住 `100755`。

### 2.2 验证结果（2026-11-23 实测）

```
Windows  python dryrun.py     → exit 0（守卫拒绝 → 修复 → 放行闭环）
Windows  python criteria.py   → GATE-A PASS 5/5；GATE-B 如实标 BLOCKED/OPEN，退出码 2
Linux 容器（内核 microsoft-standard-WSL2）→ dryrun / criteria 同样通过，行尾全 LF
python devtools/protocol_smoke.py → 真实 WebSocket 往返 task → exec/write_file → done，PASS
git status → 干净；无 API key / private key 泄漏（git grep 已扫）
```

### 2.3 辅助资产

| 文件 | 用途 |
|---|---|
| `docs/00-接手评估.md` | 接手时的完整现状评估（风险清单 P0/P1/P2、合规性核对、命令清单） |
| `docs/01-修复与验证记录.md` | 修复前后对比、验证命令与输出结论、环境实测事实 |
| `devtools/wsl-run.sh` | WSL2 侧一键脚本：`env` / `gcp` / `hf` / `check` / `dev` / `ready` |
| `devtools/protocol_smoke.py` | 不需要模型和 Docker 的 WebSocket 协议冒烟 |
| `_ple_meta/ple-official`（工作区，**不在仓库内**） | 官方 kit 本地克隆，供离线查文档 |

> 官方 `kit/build.py` import `fcntl` → **Windows Python 跑不了 kit**；`docker build` 用路径 context → Docker-in-Docker 也不可行。所以官方链路**只能在 WSL2 的 Linux 文件系统里跑**（`eval/README.md` Platform notes 明确写了这一点）。Windows 侧只能做离线自测。

---

## 3. 未完成 / 硬缺口

| 缺口 | 影响 | 归属 |
|---|---|---|
| `artifacts/` 不存在 | `kit check` 的 artifacts 阶段、`ready to submit`、dev 分数全部为 0 | M2 |
| `kit check` 未跑 | build / listen / smoke / cancel 任一失败即**终止该次机会**，且会烧掉 3 次之一 | M1 |
| 真模型端到端未验证 | `skillkit/model.py` 的 Anthropic 原生 `tool_use` / `tool_result` 序列化、`cache_control` 只做编译级验证 | T-03 |
| dev set 29 题未跑 | 无分数、无 `manifest.json`、无法 readiness | M2 |
| F-01 合规复核未完成 | 见 §6，有**新发现** | P0 |
| Docker 只有 8 CPU / 8.3 GiB | 全量 dev set 可能 OOM（官方要求 ≥16.25 GiB） | 环境 |

---

## 4. 剩余任务清单（按执行顺序，附验收标准）

### P0 — 提交 / 判 0 风险（必须先做完）

| # | 任务 | 验收标准 |
|---|---|---|
| P0-1 | 解除 `wsl.exe` 安全策略黑名单，确认 `wsl.exe --status` 可用 | 能进 WSL2，且 `uname -r` 含 `WSL2` |
| P0-2 | Docker Desktop → Settings → Resources → Memory ≥ 16.25 GiB、CPU ≥ 6，并打开 WSL2 integration | `docker info --format '{{.MemTotal}}'` ≥ 16 GiB |
| P0-3 | 拿到 HF gated 数据集授权 + read token | `devtools/wsl-run.sh hf` 返回 `HTTP 200` |
| P0-4 | 拿到 GCP project（启用 Vertex AI + 结算）+ `gcloud auth application-default login` | `devtools/wsl-run.sh gcp` 成功、proxy `/health/liveliness` 200 |
| P0-5 | **F-01 清理（新发现，优先级上调）**：`router.py` 运行时会把各 `skills/*/SKILL.md` 开头内容读进 system prompt，而 frontmatter `covers:` 直接列了 dev task id，等于把题面指纹喂给模型；`PLE_domain_skeleton.md` 还含 baseline 的具体结论数值 | 删掉 5 个 SKILL.md 的 `covers:` task id 列表，只保留领域格式惯例；把 skeleton 中的具体数值移出仓库或明确标注为格式样本；复核 `router.path_hint()` 的工作量路径家族 +9 权重 |
| P0-6 | `kit check`（先跳过 smoke 打掉门槛，再跑全量） | 全量检查末行出现 **`ready to submit`** |
| P0-7 | 真模型跑 1~2 题，验 Anthropic 路径并校准「第 10~20 步落第一版」 | `runs/<run>/attempt1/harbor.log` 无 400/序列化异常，`results.json` 有分 |

### P1 — dev set 与产物

| # | 任务 | 验收标准 |
|---|---|---|
| P1-1 | 全量 29 题 `eval/run.py` | `artifacts/` 覆盖 29 题、`manifest.json` 有本地分数 |
| P1-2 | `eval/run.py --artifacts .` 离线重判 + `python -m kit artifacts .` | 产物规则通过，无手改痕迹 |
| P1-3 | F-02：代码与 `artifacts/` **同一个 commit** | `git log -1 --stat` 里同时含 harness 与 artifacts |
| P1-4 | 推送到 GitHub，匿名 clone 验证可拉取 | `git clone https://github.com/<owner>/<repo>` 成功 |

### P2 — 提分（README 已自述，不阻塞提交）

- specgen 4 道 no-path 题（offset / footing / solar×2）：改为首轮 `exec` 读全 `task.md` 后重解析；`task.md` 不在 workdir 根目录时会失效。
- `guard` 的 `zip_soft` 一律 WARN → 按题面措辞升级为硬判。
- `model.py` 的 `max_tokens=8000` 偏保守（官方建议 Claude 给 32000）、`httpx` 超时 600 s 可能与最长推理冲突；对 400 直接 raise 是对的（官方「不要重试 400」）。
- 「第 10~20 步落第一版」是从 84 步 baseline 反推的推断值，需真模型校准。

> ⚠️ **每次改 `serve.py` / `skillkit/` / `skills/` 之后，`artifacts/` 必须全量重跑**（F-02：产物必须来自所提交的 harness + 所声明的 model_api）。所以 P0-5 的合规清理务必在 P1-1 之前做完。

---

## 5. 阻塞项：需要人本人操作（我无法代做）

1. **解除 `wsl.exe` 黑名单**：安全中心 → 命令安全 → 程序黑名单，移除 `wsl.exe`；可能需要重开会话。2026-11-23 复核仍被拦。
2. **HuggingFace 登录与条款同意**：数据集 `google/physical-engineerings-last-exam` 是 gated，条款与「Agree and access」只对登录账号可见，同意时会把用户名/邮箱共享给 Google，必须本人操作。之后在 HF 设置里建 **Read** token。浏览器页可达，但 CLI 侧 `huggingface.co` 经代理 502 / 直连超时（需排查网络，或预先下载任务目录用 `--tasks-dir`）。
3. **GCP**：提供 `VERTEXAI_PROJECT`（启用 Vertex AI + 结算账号），并在 WSL 里 `gcloud auth application-default login`。本机 `gcloud` 未安装、无任何 `MODEL_PROXY_*` 或自有模型 key。
4. **Docker 内存**：当前 8.3 GiB，需调到 ≥16.25 GiB。
5. **提交动作**：3 次机会是总量、同一时间只能有一次在队列；最终提交由本人在比赛站点操作（具体方式官方尚未公布）。

---

## 6. 规则红线（提交前逐条打勾）

- [ ] **F-01**：不硬编码答案、不检测特定 task 来分支、harness 不读取 dev graders / reference files，也不在 build/run 时读取自己的 `artifacts/`。当前灰区见 P0-5。
- [ ] **F-02**：`artifacts/` 必须由 `eval/run.py` 从**所提交的 harness**、用 `submission.yaml` 声明的 `model_api` 跑出；禁止手改、禁止别的模型/别的 harness 产出。
- [ ] `submission.yaml` 的 `model_api` 必须与实际调用一致（违反即失格）。
- [ ] 仓库内**不得有任何 API key / private key**；`local.env` 只放 `~/ple-work/`，权限 600，绝不放进仓库。
- [ ] 参赛仓库**根目录就是 entry**，所有内容已提交，工作区干净；`install` / `serve` 脚本 LF 行尾、`serve.py` / `dryrun.py` 保持 0755。
- [ ] 只用 `model_api` 指定的端点，不绕过 egress proxy、不访问模型端点以外的网络、不检查 grading 脚本。
- [ ] 提交是**单个 commit**；不要在 Windows 上做最终构建/提交（行尾、权限位、Docker 三个坑）。
- [ ] 全量 `kit check` 末行 `ready to submit` 才动用一次机会；`--no-smoke` 的检查**永远不会**打印 `ready to submit`（官方设定），别误判。

---

## 7. 运行手册（WSL2）

```bash
# 在 WSL2 的 Linux 文件系统里（不要 /mnt/c），拿到脚本：
S=~/ple-work/ple-skill/devtools/wsl-run.sh      # 或先从 Windows 侧复制
bash $S env       # 生成 ~/ple-work/local.env（chmod 600，含随机 MODEL_PROXY_KEY）
                  #   填 VERTEXAI_PROJECT、HF_TOKEN 两个 REPLACE_WITH_ 占位
bash $S gcp       # gcloud ADC 登录（浏览器交互，本人操作）
bash $S hf        # 校验 HF gated 授权（HTTP 200）
bash $S check     # uv sync + harbor + model_proxy + kit check --no-smoke --cancel-test
bash $S dev       # 先 1~2 题验真模型，再全量 29 题，产出 artifacts/
bash $S ready     # kit artifacts + 全量 kit check（末行 ready to submit）
```

等价的手动命令（出错时逐条排）：

```bash
cd ~/ple-work/ple-official
uv tool install harbor==0.20.0 --with websockets && uv sync
MODEL_PROXY_HOST=0.0.0.0 MODEL_PROXY_PORT=4000 \
VERTEXAI_PROJECT=<id> MODEL_PROXY_KEY=<key> kit/model_proxy/start.sh &
uv run python -m kit check ~/ple-work/ple-skill --env-file ~/ple-work/local.env --no-smoke --cancel-test
uv run python -m kit check ~/ple-work/ple-skill --env-file ~/ple-work/local.env
uv run python eval/run.py ~/ple-work/ple-skill --env-file ~/ple-work/local.env \
    --tasks data-center-site-model,engineers-estimate-check --trials 1
uv run python eval/run.py ~/ple-work/ple-skill --env-file ~/ple-work/local.env
uv run python -m kit artifacts ~/ple-work/ple-skill
uv run python eval/run.py --artifacts ~/ple-work/ple-skill --env-file ~/ple-work/local.env
```

Windows 侧随时可跑（不需要 Docker / key）：

```bash
python dryrun.py
python criteria.py                       # 缺 29 题数据时应报 BLOCKED，不是 PASS
python devtools/protocol_smoke.py        # 真实 WebSocket 往返
```

`eval/run.py` 的 judge 优先级：`JUDGE_BASE_URL`+`JUDGE_API_KEY` → `MODEL_PROXY_URL`+`MODEL_PROXY_KEY`（本项目走这条）→ 自有模型 key；`JUDGE_MODEL` 默认 `claude-opus-5-5`。proxy 必须 bind `0.0.0.0`，否则 Linux 上 Docker bridge 连不到 `127.0.0.1`。

---

## 8. 定义完成（DoD）

```
[ ] P0-5 F-01 清理已完成并复核
[ ] wsl-run.sh check 全绿：build / listen / smoke / mcp / cancel 全过
[ ] 真模型 1~2 题成功（Anthropic 原生路径无 400 / 无序列化异常）
[ ] artifacts/ 覆盖 29 题、由 eval/run.py 导出、manifest.json 有分数
[ ] eval/run.py --artifacts 重判通过；kit artifacts 通过
[ ] 代码 + artifacts/ 同一 commit，git status 干净，无 key，LF + 0755 正确
[ ] 全量 kit check 末行 "ready to submit"
[ ] 仓库已推送 GitHub，匿名 clone 可拉取
[ ] 在比赛站点用一次提交机会正式提交（本人操作）
```

只要其中任一项未打勾，**不要提交**——一次 build/smoke 失败就终止该次机会。

---

## 9. 路径与账号地图

| 用途 | 位置 |
|---|---|
| 本仓库（GitHub） | `https://github.com/songconmaisaix31-design/ple-skill` |
| 本仓库（Windows 本地） | `C:\Users\DW\WorkBuddy\2026-11-22-23-52-42\ple-skill` |
| 工作区根目录（评估报告原件、官方 kit 克隆） | `C:\Users\DW\WorkBuddy\2026-11-22-23-52-42\` |
| 官方 kit（WSL2） | `~/ple-work/ple-official`（`github.com/google-research/ple`） |
| 参赛仓库（WSL2） | `~/ple-work/ple-skill`（**必须在 Linux 文件系统**） |
| 密钥 | `~/ple-work/local.env`（600，绝不入库） |
| Kaggle | `ktdkydylc`；CLI 用 OAuth 登录，凭据在 `C:\Users\DW\.kaggle\credentials.json` |
| GitHub | `songconmaisaix31-design`；`gh` 已登录（token scopes: repo / workflow / gist / read:org） |

## 10. 待决策 / 未决问题

- 最终提交仓库是否就直接用本仓库？官方要求「匿名可克隆的单个 commit」，本仓库为 public，符合；但 `docs/`（含 baseline 数值）与 `devtools/` 是工程笔记，**正式提交前建议精简或加合规说明**。
- 比赛站点的**具体提交方式官方尚未公布**，需持续关注 `ple-bench.com`。
- `ple-template`（原 Linux 环境的 29 题题面 + baseline artifacts）**不在本次解压包里**；README 的 25/29、23/29、17 PASS/2 WARN/5 FAIL 因此在本机无法复现。`criteria.py --template` 默认仍指向 `/home/user/work/ple-template`，有数据时应显式传路径。
- 若 HF 网络始终不通，退路是预先下载任务目录后用 `eval/run.py --tasks-dir DIR`。
- 本机 WSL2 / Docker / 凭据到位后，**优先跑 `check` 而不是 `dev`**；顺序反了会在没验证 build 的情况下白烧几小时机时。

---

## 附：不要做的事

- 不要手工创建或编辑 `artifacts/` 里任何文件（F-02 直接失格）。
- 不要用 `openai/<model>` / 自有 key 的本地 run 产物冒充正式产物（`model_api` 必须一致）。
- 不要在改完 harness 后沿用旧 artifacts。
- 不要把 `local.env`、`HF_TOKEN`、`MODEL_PROXY_KEY`、Kaggle `credentials.json` 提交进任何仓库。
- 不要在 Windows 上跑官方 kit / 做最终构建。
- 不要相信 `criteria.py` 在缺 29 题数据时的 PASS（已修，但仍应看输出状态而不是只看退出码）。
