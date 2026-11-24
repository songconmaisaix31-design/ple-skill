# GOAL & ACCEPTANCE CRITERIA

> **状态说明（2026-11-23）**：下表「当前」列是 v1 设计稿在**有 baseline artifacts 的原 Linux 环境**下量到的目标值；本机缺 `ple-template`，`criteria.py` 会如实把 G-05~G-08 判为 **GATE-D BLOCKED**，而不是 PASS。**实际状态一律以 `python criteria.py` 输出与 `HANDOFF.md` 为准**。G-07 的 ground truth 已改为仓库外 `--truth` 显式传参。

竞品：Physical-Engineering's Last Exam（Google 赞助，2026-11-09 → 2027-01-05）。
提交形态：一个 GitHub commit（根目录 `submission.yaml` + `serve.py` + 同 commit 的 `artifacts/`）。
评分：交付物的精确路径/文件名/格式/内容占绝大多数分；rubric judge 另读 `done.final_message`。

---

## 目标（一句话）

在 2027-01-05 前，提交一个**能自己产出合格交付物**的 harness：它在 dev set 上可复现地得分，
并在 hidden test 的 3 次评分里至少完成一次完整评分、不因工程问题（构建失败 / 未监听 / 超时
不 `done`）拿 0 分。

目标不是"赢"，是**先把 0 分风险全部消掉**，再谈分数。先用官方套件验证产物和容器，再提交 Kaggle Writeup。

---

## 判据分两层

`python3 criteria.py` 是可执行版本，本文件是它的语义说明。退出码：`0`=A 层全过，`1`=A 层有硬伤，
`2`=A 层过但还不能提交（B 层未开）。

### GATE-A：代码与仓库自洽（本地即可完成，无 Docker、无 key）

| ID | 判据 | 怎么验证 | 当前 |
|---|---|---|---|
| G-01 | 根目录含 `submission.yaml` / `serve.py` / `requirements.txt` / `skillkit/` | `criteria.py` | PASS |
| G-02 | `submission.yaml` 合法：`name` 匹配 `[a-z0-9-]{2,39}`、`model_api` 前缀合法、`serve` 含 `{src}`、无未知顶层键、≤16 KiB | `criteria.py` | PASS |
| G-03 | `.env` 以外无 API key 泄漏（扫 `sk-` / `AKIA` / `ghp_`） | `criteria.py` | PASS |
| G-04 | 全部 Python 文件可编译 | `py_compile` | PASS |
| G-05 | 29 道 dev 题**全部**能路由到 `skills/` 下真实存在的目录 | `criteria.py` | PASS 29/29 |
| G-06 | specgen 从 instruction 解出交付路径 ≥ 25/29 | `criteria.py` | PASS 25/29 |
| G-07 | router 细领域判定 ≥ 23/29（与**仓库外** `--truth` 指定的 ground truth 比） | `criteria.py` | 历史值 23/29；本机需外部数据复验 |
| G-08 | guard 对 baseline 真实产出的回归 ≥ 19/24 PASS/WARN | `criteria.py` | 历史值 19/24；本机需外部数据复验 |
| G-09 | `dryrun.py` 闭环：守卫拒绝 → 强制修复 → 放行，退出码 0 且交付物存在 | `python3 dryrun.py` | PASS |
| G-12 | F-01 静态合规：无 dev 题指纹、不读 reference / 自己的 `artifacts/` | `devtools/f01_check.py` | PASS 8/8（含官方 29 个 task id 精确比对） |

**GATE-A 全过 = 代码层面没有自相矛盾。** 这一层不需要 Docker，可以随时重跑，改动后必须重跑。
实际 `criteria.py` 中 G-05~G-08 归入 **GATE-D**（依赖外部 dev 数据），缺数据时为 BLOCKED；GATE-A 现为 6 项（G-01~G-04 / G-09 / G-12）。

### GATE-B：可提交（需 Docker + 真模型端点）

| ID | 判据 | 怎么验证 | 当前 |
|---|---|---|---|
| G-10 | `artifacts/` 至少一题可用；全量覆盖为质量目标；大小、文件数量与归档格式由官方套件核对 | `python3 -m kit artifacts <repo>` | BLOCKED |
| T-01 | `kit check` 八个阶段（submission.yaml / files / .env / build / model / listen / smoke / cancel）全 PASS | `uv run python -m kit check <repo> --cancel-test` | BLOCKED |
| T-02 | 官方导出与重评通过，报告实际覆盖及 29 题均分 | `uv run python eval/run.py <repo>` | BLOCKED |
| T-03 | 真模型端到端：`serve.py` 连上 `MODEL_BASE_URL`，单题跑完并发 `done` | 起本地 evaluator 或 `kit check` 的 smoke | BLOCKED |
| T-04 | dev 分数 ≥ baseline 参照（同题同判据下的 baseline 产出） | `eval/run.py --artifacts` | TODO |
| F-01 | 无按题指纹分支：不出现"若 instruction 含 X 则输出答案"这类以 task 身份为条件的逻辑 | 人工复核 + `grep` 变量名 | TODO |
| F-02 | `artifacts/` 是提交版 harness 的原样产出，`manifest.json` 哈希与代码同 commit | `kit check` 的 artifacts 阶段 | TODO |

**GATE-B 全过 = 可以动用一次提交机会。** B 层任何一项未过，提交就是烧机会。

---

## 里程碑

| 里程碑 | 内容 | 完成判据 | 状态 |
|---|---|---|---|
| M0 | skill 库 29/29 + specgen + harness + 守卫 | GATE-A 全 PASS | **已完成**（10/10） |
| M1 | 在有 Docker 的机器上过 `kit check` | T-01 PASS | 待做 |
| M2 | 真模型跑完 dev set，产出 `artifacts/` | G-10 / T-02 / T-03 PASS | 待做 |
| M3 | 正式提交，3 次机会内完成一次完整评分 | T-04 + F-02 PASS，且提交后状态到 `scored` | 待做 |

M1 的前置是环境（Docker daemon + `uv` + `harbor==0.20.0`），与代码无关。
M2 的前置是模型 key 与一次预算判断：全程 6 小时/题 × 29 题 × 3 次 hidden test 是真实成本。

---

## 硬约束（违反即失去资格，不是"扣分"）

1. 不硬编码任何 dev/hidden 题答案，不按题面指纹分支逻辑。
2. 不绕过网络限制、不窥探评测脚本、不改评测容器。
3. `artifacts/` 必须是提交版 harness 的真实产出；改代码就重跑全量 dev，再 `git add -A`。
4. 一次只提交一个模型（`submission.yaml` 的 `model_api` 必须与实际调用的模型一致）。
5. 同一时间只能有一次提交在队列/评测中；3 次机会是总量。

## 非目标（明确不做）

- 不追求单个领域做到极致（29 题跨 8 个专业，先保证每题都"有交付、能打开、名字对"）。
- 不为提分引入需要联网的外部服务（serve 容器只可达模型端点，task 容器完全无网）。
- 不做多模型 ensemble（规则不允许一次提交多个模型）。
- 不在 hidden test 上做任何形式的探测。

---

## 每轮改动的收尾规则

任何代码改动后，按顺序执行：

```bash
python3 criteria.py          # 必须退出码 0 或 2，不能是 1
python3 dryrun.py            # 闭环仍成立
git add -A && git commit -m "<what changed>"
```

只要改了 `serve.py` / `skillkit/` / `skills/`，`artifacts/` 就必须重跑——否则 F-02 直接失效，
提交会被判为"代码与产物不匹配"。
