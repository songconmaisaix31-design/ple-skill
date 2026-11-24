# PLE-Bench 参赛 harness — 剩余任务交接文档

> 交接时间：2026-11-23（GMT+8） · 交接对象：下一位接手者 / 下一轮会话
> 本文件是**当前唯一的状态基准**。`README.md` 里的「runs the dev set」与「三项指标都在 29 道真实 dev 题上量过」是上一版设计稿的措辞：**指标来自对 baseline artifacts 的离线静态回归，不是本 harness 跑过 dev set**。以本文和 `GOAL.md` 为准。
>
> **执行环境约束（2026-11-23 追加）**：本机没有本地模型，只能用**云端模型 API + 云端 Coding Agent**。据此新增 **§11 纯云端方案**；§5 的阻塞项与 §7 的本机 WSL 假设已按该约束修订。**官方路线本来就是云端模型，不需要本地模型**——详见 §11.1。
>
> **F-01 合规清理（2026-11-23 追加）**：**P0-5 已完成** —— 运行时题面指纹已清除、baseline 反推数据已移出参赛仓库，静态自检 **8/8 PASS**（含官方 29 个 dev task id 精确比对），`criteria.py` GATE-A **6/6**。处置清单与提交前剩余人工项见 `docs/02-合规说明.md`。

---

## 0. 30 秒接手

| 项 | 现状 |
|---|---|
| 代码 | ✅ 可编译、离线闭环自测通过、协议往返冒烟通过、已推送 GitHub |
| `kit check` | `submission.yaml` 通过，模型设置缺少 `MODEL_PROXY_URL` 和 `MODEL_PROXY_KEY`。独立执行 `kit build` 确认可执行环境没有 Docker |
| 真模型端到端 | 原生 Claude、会话取消和多工具回复通过本地协议模拟。官方 task 容器和真实模型待跑 |
| `artifacts/` | ❌ **目录不存在**，必须由 `eval/run.py` 生成，禁止手写 |
| dev 分数 | **未测**，暂无官方 `results.json` 或 `artifacts/` |
| F-01 合规 | ✅ **已清理**：运行时指纹、baseline 反推数据已处置，静态自检 8/8（`docs/02-合规说明.md`） |
| 截止 | 2027-01-06 07:59:59（北京时间），以 Kaggle Timeline 为准 |
| 当前最该做 | 选一台**能跑 Docker 的云主机** → 跑 `cloud-preflight.sh` → 起云端模型代理 → `kit check` 打掉判 0 门槛 → 再上 dev set（§11） |

先取得一次计分的公开题试跑，再固定 harness 版本跑全量。离线验证和官方配置校验只证明接入正确性的一部分。

## 初赛评分证据

| 评分项 | 分值 | 从评测保留的证据 |
|---|---:|---|
| 洞察与失败分析 | 25 | 真实失败轨迹和受控消融。同一模型、同一题、同一 judge 下单独开关一个机制 |
| 工程推理 | 25 | 选一道公开题，比较有执照工程师与 harness 的流程、依据、验算和缺漏 |
| 跨模型泛化 | 15 | 同一 harness 在两种模型上各跑 29 题，记录逐题成绩和 token |
| 效率与扩展性 | 20 | 记录调用、token、耗时、并发规模和得分，标出增加预算后收益趋缓的位置 |
| 表达与图表 | 15 | Writeup 少于 2,000 词，准备架构图、分数对成本图、失败分布图和独立封面 |

开发顺序为 WSL 单题试跑、主模型 29 题基线、同版本第二模型 29 题，再从真实故障中选择一个改动做消融。比较时固定官方任务数据版本和 judge，记录仓库 commit。第二模型在独立工作树配置，并用官方 `--no-export` 保留对照结果，避免覆盖参赛产物。

从 WSL 的正式题运行目录取得 `results.json` 后，可比较分数、覆盖、失败类型、token 和耗时。试跑只报告选中题的分数，配对分差只统计两边都已评分的任务。

```bash
python3 devtools/scorecard.py baseline=/path/to/results.json candidate=/path/to/results.json --details
```

评分与交付以 [Kaggle Evaluation](https://www.kaggle.com/competitions/physical-engineerings-last-exam/overview#evaluation) 为准。当前参赛分支按 [Google 官方 kit 公平竞赛规则](https://github.com/google-research/ple/blob/main/docs/rules.md) 使用与申报一致的模型生成提交产物。

---

## 1. 事实基线（不要凭记忆改）

| 项 | 值 | 来源 |
|---|---|---|
| 比赛 | Physical-Engineering's Last Exam (PLE-Bench)，`ple-bench.com` / `github.com/google-research/ple` | 官网 |
| Kaggle 入口 | `physical-engineerings-last-exam`；账号 **ktdkydylc 已报名**（`userHasEntered=True`） | Kaggle CLI 实测 |
| 周期 / 奖金 | 北京时间截止 **2027-01-06 07:59:59** / 400K USD（250K / 100K / 50K） | Kaggle |
| 题量 | 85 题 = 29 dev（公开）+ 56 hidden；dev 数据集 955 MB（12 checks / 14 rubric / 3 checks-judge） | 官网 / HF |
| 提交形态 | 在 Kaggle 提交 GitHub commit，包含 `submission.yaml`、harness 和同一 commit 的 `artifacts/`，另交 Writeup | Kaggle、`docs/rules.md`、`kit/README.md` |
| 模型 | `submission.yaml` = `google-cloud/claude-opus-5-5`（8 个赞助模型之一）；**模型始终在云端**，本地只需一个 LiteLLM 转发进程，经 `MODEL_PROXY_URL` + `MODEL_PROXY_KEY` 访问 | `docs/models.md` |
| 自有云端 key | 官方明确允许「任意 LiteLLM / OpenAI-compatible 代理 serve 同名模型」，甚至举例「把 `claude-opus-5-5` 路由到自己的 Anthropic key」；**`model_api` 不改** | `docs/models.md` §Running google-cloud models on your machine |
| 不能改的 | `anthropic/<model>` / `openai/<model>` / `gemini/<model>` / `openai-compatible/<model>` 都是 **local runs only**，`kit check` 永不报 `ready to submit` | `docs/models.md`、`kit/README.md` |
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
| `05f90e3` | 文档提交：`HANDOFF.md` / `docs/` / `devtools/` / README 状态说明 |
| `b7fcc14` | 文档修订：记录交接提交号 |
| `990bf5f` | 纯云端方案：HANDOFF §11、`cloud-preflight.sh`、`litellm-selfhosted.yaml.example`、运行脚本泛化 |
| **本轮提交** | **F-01 合规清理**：5 个 SKILL.md 去 `covers:` 与题面指纹、`router.path_hint()` 降权、移出 `PLE_domain_skeleton.md` / `skeleton2.json` / `_build/`、新增 `devtools/f01_check.py` 与 `docs/02-合规说明.md`、`criteria.py` 外部化数据源与新增 G-12、writeups 中性化 |

`084a58b` 修掉的 5 个问题：
1. `serve.py`：`ping_interval=20, ping_timeout=60` → **`ping_interval=None`**。官方 `docs/protocol.md` 明确要求关闭 keepalive（单条 `exec` 上限 600 s，长命令期间心跳会判断连、该题直接算 harness 失败）。这是原项目最高优先级的判 0 风险。
2. `guard.py` / `transport.py`：去掉硬编码 `/tmp/ple_validate.py`，改由 transport 提供 `scratch_path()` 与 `python_cmd`。评测容器仍走 `/tmp`（Linux 有 1 GB 可写），本地 dryrun 走 workdir + 当前解释器，Windows 不再炸。
3. `dryrun.py`：stub 命令改成跨平台 `python helper.py <verb>`。
4. `criteria.py`：新增 A / D / B / E 分层；缺 29 题数据时判 **BLOCKED**，不再 `0/0` 假 PASS；Docker 探测改 `shutil.which`（原来用 `bash -lc` 会误触安全策略）。
5. `.gitattributes`：源码强制 LF，默认 `-text` 保护未来 `artifacts/` 的字节哈希。git 配 `core.filemode=false` / `core.autocrlf=false` / `core.symlinks=true`；`serve.py`、`dryrun.py` 保住 `100755`。

### 2.2 验证结果（2026-11-23 实测）

```
Windows  python dryrun.py     → exit 0（守卫拒绝 → 修复 → 放行闭环）
Windows  python criteria.py   → GATE-A PASS 6/6（含 G-12）；GATE-D/B 如实标 BLOCKED/OPEN，退出码 2
Linux 容器（内核 microsoft-standard-WSL2）→ dryrun / criteria 同样通过，行尾全 LF
python devtools/protocol_smoke.py → 真实 WebSocket 往返 task → exec/write_file → done，PASS
python devtools/f01_check.py --dev-set <official eval/dev_set.yaml> → F-01 静态合规 PASS 8/8
                                     （29 个 dev task id 精确比对，runtime 中 0 命中）
git status → 干净；无 API key / private key 泄漏（git grep 已扫）
```

### 2.3 辅助资产

| 文件 | 用途 |
|---|---|
| `docs/00-接手评估.md` | 接手时的完整现状评估（**历史快照**，状态以本文件为准；风险清单 P0/P1/P2、合规性核对、命令清单） |
| `docs/01-修复与验证记录.md` | 修复前后对比、验证命令与输出结论、环境实测事实 |
| `docs/02-合规说明.md` | **F-01 / F-02 合规说明**：规则边界、运行时文件白名单、本次清理清单、提交前人工项 |
| `devtools/wsl-run.sh` | 通用 Linux 一键脚本（文件名沿用）：`env` / `gcp` / `hf` / `check` / `dev` / `ready`；WSL2 与云主机都能用 |
| `devtools/cloud-preflight.sh` | **云端环境探测**：Docker daemon、CPU/内存/磁盘、网络、工具链，输出逐项结论 |
| `devtools/f01_check.py` | **F-01 静态合规自检**（8 项；`--dev-set` 可做 29 个 task id 精确比对），已接入 `criteria.py` G-12 |
| `devtools/litellm-selfhosted.yaml.example` | 自有云端 API key 的 LiteLLM 代理配置样例（B 档，见 §11.2） |
| `devtools/protocol_smoke.py` | 不需要模型和 Docker 的 WebSocket 协议冒烟 |
| `_ple_meta/ple-official`（工作区，**不在仓库内**） | 官方 kit 本地克隆，供离线查文档 |
| `_ple_meta/f01-backup-20261123/`（工作区，**不在仓库内**） | 被移出/改写的 baseline 反推数据原件备份，仅供追溯，**不要入库** |

> 官方 `kit/build.py` import `fcntl` → **Windows Python 跑不了 kit**；`docker build` 用路径 context → Docker-in-Docker 也不成立。所以官方链路**必须在能跑 Docker daemon 的 Linux 文件系统里执行**（`eval/README.md` Platform notes）。这不一定是本机 WSL2 —— **一台云主机同样满足，且能绕开本机全部阻塞**（§11）。Windows 侧只能做离线自测。

---

## 3. 未完成 / 硬缺口

| 缺口 | 影响 | 归属 |
|---|---|---|
| `artifacts/` 不存在 | 尚无提交用产物和可报告的 dev 分数 | M2 |
| `kit check` 首次停在模型设置 | 仍需在带 Docker 与模型代理的主机执行 build / listen / smoke / cancel | M1 |
| 真模型端到端未验证 | Anthropic 原生 `tool_use` / `tool_result` 序列化、思考内容回传与用量统计已通过本地协议模拟 | T-03 |
| dev set 29 题未跑 | 无分数、无 `manifest.json`、无法 readiness | M2 |
| F-01 静态合规 | ✅ **已完成**：`f01_check.py` 8/8、GATE-A 6/6。剩余为**提交前人工项**：复核运行日志、把仓库重建为单个 commit 清除历史里的 reference 数据（`docs/02-合规说明.md` §6） | P0 |
| git 历史残留 | 早期提交 `17408a5` / `a58b197` 曾含 baseline 反推数据；当前 HEAD 已删除，但历史 tree 仍在。官方要求「单个 commit」→ 最终应重建历史 | P1，提交前 |
| 本机 Docker 只有 8 CPU / 8.3 GiB | 全量 dev set 可能 OOM（官方要求 ≥16.25 GiB）；**改用云主机即可解除** | 环境 |
| 云端执行环境未选定 / 未探测 | 决定 `kit check` 与 `eval/run.py` 能否跑起来；多数纯沙箱 Coding Agent **没有 Docker daemon** | P0，见 §11.3 |

---

## 4. 剩余任务清单（按执行顺序，附验收标准）

### P0 — 提交 / 判 0 风险（必须先做完）

| # | 任务 | 验收标准 |
|---|---|---|
| P0-1 | 选定**能跑 Docker daemon 的云主机**（或 WSL2），克隆本仓库与官方 kit 到 Linux 文件系统 | `bash devtools/cloud-preflight.sh` 全绿 |
| P0-2 | 云端 Docker 资源达标：≥6 CPU、**≥16.25 GiB RAM**、≈10 GB 空闲磁盘、`linux/amd64` | `docker info` 输出的内存 ≥16 GiB；`docker run --rm hello-world` 成功 |
| P0-3 | 拿到 HF gated 数据集授权 + read token | `devtools/wsl-run.sh hf` 返回 `HTTP 200` |
| P0-4 | 起**云端模型代理**：A 档 Vertex AI（GCP + ADC）或 B 档自有云端 key 经 LiteLLM（§11.2 二选一） | `/health/liveliness` 200，且 `POST /v1/messages` 对 `claude-opus-5-5` 返回 200 |
| P0-5 | ✅ **F-01 清理已完成（本轮）**：5 个 SKILL.md 去 `covers:` 与题面指纹；移出 `PLE_domain_skeleton.md` / `skeleton2.json` / `_build/`；`router.path_hint()` `+9 → +4`；`criteria.py` 外部化数据源；新增 G-12 与 `f01_check.py`；writeups 中性化 | 已达成：`python devtools/f01_check.py --dev-set <official dev_set.yaml>` → **PASS 8/8**，`criteria.py` **GATE-A 6/6**。详见 `docs/02-合规说明.md` |
| P0-6 | `kit check`（先跳过 smoke 打掉门槛，再跑全量） | 全量检查末行出现 **`ready to submit`** |
| P0-7 | WSL 先串行跑一题，验 Anthropic 路径和官方评分链路 | `runs/<run>/attempt1/harbor.log` 无 400/序列化异常，`results.json` 有实测结果 |

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

## 5. 阻塞项：需要人本人操作（已按「纯云端」约束重排）

| # | 阻塞 | 状态 / 解决方式 |
|---|---|---|
| 1 | **HuggingFace 登录与条款同意**（唯一绕不开的人工项） | 数据集 `google/physical-engineerings-last-exam` 是 gated，条款与「Agree and access」只对登录账号可见，同意时会把用户名/邮箱共享给 Google，必须本人操作；之后建 **Read** token。本机 CLI 侧 `huggingface.co` 经代理 502 / 直连超时，**换云主机后大概率自动解除**；仍不通则预先下载任务目录用 `--tasks-dir` |
| 2 | **云端模型凭据，二选一** | A：GCP 项目 + Vertex AI + 结算 + `gcloud auth application-default login`；**或** B：任意一个云端模型 API key，经 LiteLLM 代理 serve `claude-opus-5-5`（官方明文允许，§11.2）。**不需要本地模型、不需要 GPU** |
| 3 | **云主机 / Docker** | 必须有一台能真正跑 Docker daemon 的 Linux 主机（≥16.25 GiB RAM）。纯沙箱 Coding Agent 通常不满足，见 §11.3 选型表。本机 `wsl.exe` 黑名单与 8.3 GiB 内存问题**因此可以整体绕开**，不再是阻塞 |
| 4 | **提交动作** | 在 Kaggle 交经 kit 验证的提交 commit 和 Writeup，具体步骤以当期竞赛页面为准 |

> 原「解除 `wsl.exe` 黑名单」「本机 Docker 调到 16 GiB」「必须装 gcloud」三项已从阻塞清单移除：改用云主机后它们都不再必要。

---

## 6. 规则红线（提交前逐条打勾）

- [x] **F-01 静态部分**：不硬编码答案、不检测特定 task 来分支、harness 不读取 dev graders / reference files，也不在 build/run 时读取自己的 `artifacts/`。本轮已清理，`f01_check.py` 8/8、G-12 PASS；**提交前仍需人工复核运行日志与最终 commit**（`docs/02-合规说明.md` §6）。
- [ ] **F-02**：`artifacts/` 必须由 `eval/run.py` 从**所提交的 harness**、用 `submission.yaml` 声明的 `model_api` 跑出；禁止手改、禁止别的模型/别的 harness 产出。
- [ ] `submission.yaml` 的 `model_api` 必须与实际调用一致（违反即失格）；**为了接自有云端 key 而改成 `anthropic/<model>` / `openai/<model>` 等于放弃提交资格**，代理可换、`model_api` 不可换（§11.4）。
- [ ] **Coding Agent 只做开发 / 运维 / 提交代码，不能代替 harness 做题或生成 artifacts**（§11.4）。
- [ ] 若走 B 档（自有 key 代理）产出 artifacts，正式提交前用 A 档 Vertex AI 重跑一遍，或向比赛方确认通道合规（§11.4 灰区）。
- [ ] 仓库内**不得有任何 API key / private key**；`local.env` 只放 `~/ple-work/`，权限 600，绝不放进仓库。
- [ ] 参赛仓库**根目录就是 entry**，所有内容已提交，工作区干净；`install` / `serve` 脚本 LF 行尾、`serve.py` / `dryrun.py` 保持 0755。
- [ ] 只用 `model_api` 指定的端点，不绕过 egress proxy、不访问模型端点以外的网络、不检查 grading 脚本。
- [ ] 提交是**单个 commit**；不要在 Windows 上做最终构建/提交（行尾、权限位、Docker 三个坑）。
- [ ] 全量 `kit check` 末行 `ready to submit` 才动用一次机会；`--no-smoke` 的检查**永远不会**打印 `ready to submit`（官方设定），别误判。

---

## 7. 运行手册（任意 Linux + Docker：WSL2 或云主机）

WSL 先在 Linux 文件系统里运行 `check` 和 `pilot`。默认 `pilot` 只跑公开题 `wind-diaphragm-shear`，用程序化 grader、无需 LLM judge，且最多同时跑 1 题。它仍需要 Docker 和声明模型的代理。已有约 8.3 GiB Docker 内存可尝试单题，具体任务消耗以实跑为准。全量 29 题按官方指南给 Docker 至少 6 CPU 与 16.25 GiB 内存。

```bash
# 在 WSL 的 Linux 文件系统里进入要评测的仓库
export PLE_ENTRY_DIR="$PWD"
bash devtools/cloud-preflight.sh                 # 先探测环境，缺什么一目了然
S=devtools/wsl-run.sh
bash $S env       # 生成 ~/ple-work/local.env（chmod 600，含随机 MODEL_PROXY_KEY）
                  #   填 HF_TOKEN；A 档再填 VERTEXAI_PROJECT，B 档再填 ANTHROPIC_API_KEY
bash $S gcp       # 仅 A 档需要：gcloud ADC 登录（浏览器交互，本人操作）
bash $S hf        # 用已配置的 read token 校验 HF gated 授权（HTTP 200）
bash $S check     # uv sync + harbor + model_proxy + kit check --no-smoke --cancel-test
bash $S smoke     # 官方文件与 MCP 冒烟，含 cancel
bash $S pilot     # 默认跑 1 道 checks 题，结果留在官方 kit 的 runs/ 下
bash $S dev       # 全量 29 题，产出 artifacts/
# 复核后将 artifacts/ 与 harness 提交到同一 Git commit
bash $S ready     # kit artifacts + 重判 + 全量 kit check（末行 ready to submit）
```

等价的手动命令（出错时逐条排）：

```bash
cd ~/ple-work/ple-official
uv tool install harbor==0.20.0 --with websockets && uv sync
# A 档：官方 Vertex AI 代理
MODEL_PROXY_HOST=0.0.0.0 MODEL_PROXY_PORT=4000 \
VERTEXAI_PROJECT=<id> MODEL_PROXY_KEY=<key> kit/model_proxy/start.sh &
# B 档：自有云端 key，改用 litellm + devtools/litellm-selfhosted.yaml.example（§11.2）
uv run python -m kit check ~/ple-work/ple-skill --env-file ~/ple-work/local.env --no-smoke --cancel-test
uv run python -m kit check ~/ple-work/ple-skill --env-file ~/ple-work/local.env --cancel-test
uv run python eval/run.py ~/ple-work/ple-skill --env-file ~/ple-work/local.env \
    --tasks wind-diaphragm-shear --trials 1 --attempts 1 --no-export
uv run python eval/run.py ~/ple-work/ple-skill --env-file ~/ple-work/local.env
uv run python -m kit artifacts ~/ple-work/ple-skill
uv run python eval/run.py --artifacts ~/ple-work/ple-skill --env-file ~/ple-work/local.env
```

Windows 侧随时可跑（不需要 Docker / key）：

```bash
python dryrun.py
python criteria.py                       # GATE-A 6/6；缺 29 题数据时 GATE-D 报 BLOCKED，不是 PASS
python devtools/protocol_smoke.py        # 真实 WebSocket 往返
python devtools/f01_check.py             # F-01 静态合规自检（7 硬检查 + 1 SKIP）
python devtools/f01_check.py --dev-set <官方 eval/dev_set.yaml>   # 8/8，含 29 个 task id 精确比对
```

`eval/run.py` 的 judge 优先级：`JUDGE_BASE_URL`+`JUDGE_API_KEY` → `MODEL_PROXY_URL`+`MODEL_PROXY_KEY`（本项目走这条）→ 自有模型 key；`JUDGE_MODEL` 默认 `claude-opus-5-5`，judge 任务会请求 **`<model>-judge`**，所以自制代理必须同时 serve `claude-opus-5-5-judge`（§11.2）。proxy 必须 bind `0.0.0.0`，否则 Linux 上 Docker bridge 连不到 `127.0.0.1`。

---

## 8. 定义完成（DoD）

```
[x] P0-5 F-01 静态清理已完成并复核（f01_check.py 8/8、GATE-A 6/6）
[ ] cloud-preflight.sh 全绿：Docker daemon / ≥16.25 GiB / 网络 / 工具链
[ ] 模型代理就绪：/health/liveliness 200，/v1/messages 对 claude-opus-5-5 返回 200
[ ] wsl-run.sh check 全绿：build / listen / smoke / mcp / cancel 全过
[ ] 真模型 1~2 题成功（Anthropic 原生路径无 400 / 无序列化异常）
[ ] artifacts/ 覆盖 29 题、由 eval/run.py 导出、manifest.json 有分数
[ ] eval/run.py --artifacts 重判通过；kit artifacts 通过
[ ] 代码 + artifacts/ 同一 commit，git status 干净，无 key，LF + 0755 正确
[ ] 仓库重建为单个 commit：git 历史中不再含 baseline 反推数据（docs/02-合规说明.md §6）
[ ] 提交前人工复核运行日志：harness 未读取 artifacts/ 或 graders
[ ] 全量 kit check 末行 "ready to submit"
[ ] 仓库已推送 GitHub，匿名 clone 可拉取
[ ] 若走 B 档，提交前已用 A 档重跑 artifacts 或已向比赛方确认
[ ] 在比赛站点用一次提交机会正式提交（本人操作）
```

完整 29 题覆盖是本项目的提分目标。官方允许先导出并提交部分任务，缺题按零计。以提交版本的实际模型、官方导出、完整 kit check 和 Kaggle 当期要求为准。[官方产物规范](https://github.com/google-research/ple/blob/main/docs/artifacts.md)

---

## 9. 路径与账号地图

| 用途 | 位置 |
|---|---|
| 本仓库（GitHub） | `https://github.com/songconmaisaix31-design/ple-skill` |
| 本仓库（Windows 本地，仅离线开发） | `C:\Users\DW\WorkBuddy\2026-11-22-23-52-42\ple-skill` |
| 工作区根目录（评估报告原件、官方 kit 克隆） | `C:\Users\DW\WorkBuddy\2026-11-22-23-52-42\` |
| 官方 kit（云主机 / WSL2） | `~/ple-work/ple-official`（`github.com/google-research/ple`） |
| 参赛仓库（云主机 / WSL2） | `~/ple-work/ple-skill`（**必须在 Linux 文件系统**） |
| 密钥（云主机侧） | `~/ple-work/local.env`（600，绝不入库）：`HF_TOKEN` / `MODEL_PROXY_KEY` / A 档 `VERTEXAI_PROJECT` 或 B 档 `ANTHROPIC_API_KEY` |
| Kaggle | `ktdkydylc`；CLI 用 OAuth 登录，凭据在 `C:\Users\DW\.kaggle\credentials.json` |
| GitHub | `songconmaisaix31-design`；`gh` 已登录（token scopes: repo / workflow / gist / read:org） |

## 10. 待决策 / 未决问题

- **模型通道选 A 还是 B？**（§11.2）A 需 GCP 项目 + 结算但零争议；B 只需一个云端 API key，但产物通道存在评审疑义。
- **云端 Coding Agent 具体是哪种环境？** 关键只看一件事：**能否跑 Docker daemon**（§11.3 选型表）。若无 Docker，只能让它改代码，eval 要交给另一台机器。
- 最终提交仓库是否就直接用本仓库？官方要求「匿名可克隆的单个 commit」，本仓库为 public，符合。`docs/` / `devtools/` 是工程笔记，已在 `docs/02-合规说明.md` 声明**不参与 runtime**；但**早期 git 提交里曾含 baseline 反推数据，当前 HEAD 已删除、历史 tree 仍在** —— 稳妥做法是从清理后的 tree 重建为单个全新 commit（或 squash 后 force push），否则仍建议精简/重建。
- 比赛提交与时间线以 Kaggle 当期页面为准。
- `ple-template`（原 Linux 环境的 29 题题面 + baseline artifacts）**不在本次解压包里**；README 的 25/29、23/29、17 PASS/2 WARN/5 FAIL 因此在本机无法复现。本轮已把 `criteria.py --template` 默认值改为**空**、并新增 `--truth`（也可用 `PLE_TEMPLATE` / `PLE_TRUTH` 环境变量），仓库内不再内置任何 reference 路径；有数据时显式传外部路径。
- 若 HF 网络始终不通，退路是预先下载任务目录后用 `eval/run.py --tasks-dir DIR`。
- 环境就绪后**优先跑 `check` 而不是 `dev`**；顺序反了会在没验证 build 的情况下白烧几小时机时。

---

## 11. 纯云端方案（无本地模型 / 无本机 WSL）

> 2026-11-23 追加，对应约束：「没有本地模型，只能用云端模型 + 云端 Coding Agent」。
> **结论：这个约束不构成障碍，反而一次性绕开了本机 `wsl.exe` 黑名单、8.3 GiB 内存、`fcntl` / Windows 三个坑。** 但引入三条新红线（§11.4）。

### 11.1 先纠正误解：官方路线本来就是云端模型

`kit/model_proxy/start.sh` 启动的是一个 **LiteLLM 转发进程**（无模型权重、CPU/内存开销极小），后端指向 Google **Vertex AI 云端**的 `claude-opus-5-5`；正式评测时 Google 的 model gateway 同理。所以**「没有本地模型」从来不是问题**，需要的只是「一个能访问云端模型端点的进程」。

`docs/models.md`「Running google-cloud models on your machine」原文：

> *"Any other LiteLLM or OpenAI-compatible proxy that serves those names works too (for example, routing `claude-opus-5-5` to your own Anthropic key), as long as it also speaks the native API your harness uses."*

即：**`submission.yaml` 保持 `google-cloud/claude-opus-5-5` 不动**，`MODEL_PROXY_URL` 可以指向任何 serve 同名模型的代理，包括把 `claude-opus-5-5` 路由到你自己的云端 API key。**不需要 GCP 结算也能跑通 `kit check` 与 `eval/run.py`。**

### 11.2 两条模型通道（二选一）

| | **A：Vertex AI（最稳）** | **B：自有云端 API key（无 GCP 结算）** |
|---|---|---|
| 后端 | 官方 `kit/model_proxy/start.sh` + `VERTEXAI_PROJECT` + gcloud ADC | 自制 LiteLLM config，把 `claude-opus-5-5` 映射到自有 key |
| 需要 | GCP 项目 + Vertex AI + 结算账号 | 一个云端模型 API key |
| 与评测通道 | 完全一致 | 同款模型、不同计费通道 |
| 提交争议 | 无 | ⚠️ 见 §11.4 第 3 条 |
| 配置 | 官方 `kit/model_proxy/config.yaml` 现成 | `devtools/litellm-selfhosted.yaml.example` |

**B 档的 4 个硬性技术条件**（否则 kit check 的 model / smoke 阶段直接失败）：

1. 代理必须提供 **Anthropic Messages 原生端点 `POST /v1/messages`**。评测器对 Claude 模型注入 `ANTHROPIC_BASE_URL` + `ANTHROPIC_API_KEY`（`docs/models.md`「What your server receives」），`skillkit/model.py::from_env()` 因此置 `mode="anthropic"`。只支持 OpenAI Chat Completions 的网关会在这一步 404。
2. 代理必须同时 serve **`claude-opus-5-5` 与 `claude-opus-5-5-judge`**。`eval/run.py` 在 rubric / checks-judge 任务上请求 `<model>-judge`，缺这条会 404。
3. `general_settings.master_key` = `MODEL_PROXY_KEY`，与 `--env-file` 里的一致。
4. 监听 **`0.0.0.0`**（不是 `127.0.0.1`），否则 Linux 上 Docker bridge 连不到。

启动与自检（云主机）：

```bash
export MODEL_PROXY_KEY=$(openssl rand -hex 24)
export ANTHROPIC_API_KEY=...        # 只进 local.env，绝不入库
uv run --no-project --python 3.11 --with 'litellm[proxy]==1.90.0' litellm \
  --config devtools/litellm-selfhosted.yaml.example --host 0.0.0.0 --port 4000 &

curl -s http://127.0.0.1:4000/health/liveliness
curl -s -H "Authorization: Bearer $MODEL_PROXY_KEY" \
     -H 'content-type: application/json' -H 'anthropic-version: 2023-06-01' \
     -d '{"model":"claude-opus-5-5","max_tokens":16,"messages":[{"role":"user","content":"ping"}]}' \
     http://127.0.0.1:4000/v1/messages | head -c 300
```

> 若 LiteLLM 版本的 `/v1/messages` 不可用，换一个同时支持两种协议的网关，或把 `skillkit/model.py` 改走 OpenAI 兼容分支——**但改完必须重跑 `protocol_smoke.py`、全量 `kit check` 与全量 dev set**。

### 11.3 云端 Coding Agent 的真正硬门槛是 Docker，不是模型

`eval/run.py` 用 Harbor 0.20.0 起 build / serve / task / verifier 四类容器，需要**能真正运行 Docker daemon 的 Linux 主机**：≥6 CPU、**≥16.25 GiB RAM**、≈10 GB 空闲磁盘（镜像约 17 GB）、`linux/amd64`、能访问 `huggingface.co` / 模型端点 / `github.com`、能长时间运行（29 题 × 360 分钟）。

| 云端环境 | 可行性 | 说明 |
|---|---|---|
| 云 VM（16–32 GiB，自装 Docker） | ✅ **最稳，推荐** | 先跑 `bash devtools/cloud-preflight.sh` |
| 自建 / self-hosted Actions runner（有 Docker） | ✅ 可行 | 密钥放 CI secrets；注意单 job 6 h 上限，可按 task 拆 matrix |
| GitHub Codespaces 32 GB + Docker-in-Docker | ⚠️ 可行但受限 | 需选大机型、确认 dockerd 可用、留意超时与计费 |
| 纯沙箱 Coding Agent（在线 IDE / Claude Code web / Codex cloud，无 Docker daemon） | ❌ **不能跑 eval** | 只能用来**改代码 + commit/push**；`eval/run.py` 必须交给有 Docker 的机器 |

### 11.4 三条不能踩的红线

1. **Coding Agent 不能代替 harness 产出 artifacts**。F-02：`artifacts/` 必须由 `eval/run.py` 从**所提交的 harness**、用声明的 `model_api` 跑出，禁止手工创建，也禁止「让 Agent 自己解 29 道题再把文件塞进 `artifacts/`」。Coding Agent 的职责是开发 / 运维 / 排错 / 提交代码，不是做题。
2. **不要为了方便把 `submission.yaml` 改成 `anthropic/<model>` / `openai/<model>` / `openai-compatible/<model>`**。`docs/models.md` 明确这些是 **local runs only**，`kit check` 对这类 entry **永远不会**报 `ready to submit`。代理可以换，`model_api` 不能换。
3. **B 档的提交合规灰区要显式处理**。官方把「任意代理路由到自有 key」写在 local runs 一节；`rules.md` 只要求 `model_api` 与实际调用的模型一致、产物来自同一 harness。同款 Claude Opus 5.5 经自有 key 跑出的 artifacts 从文本上满足，但**存在评审疑义**。稳妥做法：B 档完成开发与全量 dev set，最终提交前用 A 档（Vertex AI）重跑一遍 artifacts；或先在比赛方 FAQ / 讨论区确认。**不要默认它一定没问题。**

### 11.5 云端执行顺序

1. 云主机上 `git clone` 本仓库 + `google-research/ple`，都放 Linux 文件系统。
2. `bash devtools/cloud-preflight.sh` → 确认 Docker / 内存 / 网络 / 工具链。
3. `bash devtools/wsl-run.sh env` → 填 `HF_TOKEN`、`MODEL_PROXY_KEY`；A 档另填 `VERTEXAI_PROJECT`，B 档另填 `ANTHROPIC_API_KEY`（都在 `local.env`，权限 600，绝不入库）。
4. 起代理（A：官方 `start.sh`；B：§11.2 命令），自检 `/health/liveliness` 与 `/v1/messages`。
5. `bash devtools/wsl-run.sh hf` → `check` → 真模型 1~2 题 → `dev` → `ready`。
6. `git add artifacts && git commit && git push`，代码与产物**同一个 commit**。
7. 全量 `kit check` 末行 `ready to submit` 后，才动用提交机会。

---

## 附：不要做的事

- 不要手工创建或编辑 `artifacts/` 里任何文件（F-02 直接失格）。
- 不要把 `PLE_domain_skeleton.md` / `skeleton2.json` / `_build/` 加回参赛仓库，也不要在 SKILL.md 里重写 `covers:` 或具体题目的取值、文号、人名、日期（`docs/02-合规说明.md`）。
- 不要把 `_ple_meta/f01-backup-20261123/` 备份目录放进任何仓库或推送到 GitHub。
- 不要让云端 Coding Agent 代替 harness 做题或生成产物（§11.4）。
- 不要把 `submission.yaml` 的 `model_api` 改成 `anthropic/` / `openai/` / `openai-compatible/` 以接自有 key（会永久失去提交资格）；代理可换、声明不能换。
- 不要在改完 harness 后沿用旧 artifacts。
- 不要把 `local.env`、`HF_TOKEN`、`ANTHROPIC_API_KEY`、`MODEL_PROXY_KEY`、Kaggle `credentials.json` 提交进任何仓库。
- 不要在 Windows 上跑官方 kit / 做最终构建。
- 不要相信 `criteria.py` 在缺 29 题数据时的 PASS（已修，但仍应看输出状态而不是只看退出码）。
