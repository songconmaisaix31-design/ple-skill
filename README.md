# PLE harness

Physical-Engineering's Last Exam 参赛 harness。**spec-first + 交付物守卫**的第一版实现。

> **云端实测（2026-11-23）**　Gemma 4 26B A4B 在 GitHub Actions 的 CPU 上完成了自建梁受力计算题。第 395 秒通过 1/8 项，约 647 秒时通过 8/8 项，包含四个独立校验的数值。[运行日志](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45171069072)
> **正式开发集**　已尝试运行 `wind-diaphragm-shear`。Hugging Face 对运行器的凭据交换返回 `invalid_grant`，题目下载前流程结束。当前没有本项目的官方开发集分数或参赛 `artifacts/`。[正式题运行记录](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45167261631)
> **固定种子复验**　开发集 A/B/C 上，Gemma 首轮使用 Python 后在第 395 秒交付了 3/3 个最优解。两道新留出题各重复三次，原工具循环均分 0.00，首轮 Python 均分 0.50，三轮配对分差的样本方差为 0。提升全部来自 E；D 两组均失败。12 次运行的归档产物已独立重评。正式 PLE 开发题评分仍待数据授权。[逐次成绩、图表与证据包](docs/experiments/paired-storage-v1/README.md) · [实验方法](docs/03-validation-methods.md)
> 下文“三项指标”衡量对主办方基线产物的离线静态回归。
> 剩余任务、阻塞项、运行手册与合规红线见 **[HANDOFF.md](HANDOFF.md)**；评估原件见 `docs/00-接手评估.md`，修复记录见 `docs/01-修复与验证记录.md`，**F-01 处置说明见 `docs/02-合规说明.md`**。

设计原点：**MCP 作为中心**——serve.py 持有会话与决策循环，所有动作（exec / read_file /
write_file / mcp_call）都经由 competition protocol 走 WebSocket 回到 evaluator；MCP server
在同一循环里被唤起，而不是被降级成一个"顾问工具"。**skill 是给这个循环用的执行规范，
不是给人看的文档**；**guard 是灵魂**：交付物的路径/文件名/列头在模型开口之前就已经被写成合同。

## 为什么这样切

baseline 的平均轨迹 84 步，其中大量步数花在"我以为交付物该叫什么"。评分里交付物——
精确路径、文件名、格式、内容——占绝大多数分。所以顺序被反过来：

1. **先抽合同**（specgen）：从 instruction（必要时叠加 task.md）抽出交付路径、模式、
   必需成员、CSV 列头，在任何一次模型调用之前落盘成 `spec.json`。
2. **再路由 skill**（router）：instruction → 领域（structural / electrical / mep / civil /
   fire / cost / permit / cfd / misc）→ 该领域的文档骨架与 checklist。
3. **第 10~20 步落第一版完整可打开交付物**，然后原地迭代（官方明确建议，且 baseline
   84 步意味着这一步必须早）。
4. **每 2 步自动跑守卫**（validate.py 在 task 容器内执行），FAIL 就注入一条强制修正指令；
   `finish` 时守卫不 PASS 直接拒绝收工。
5. **熔断**：同一个合同连续拒 3 次 → 判定"合同本身抽偏了"，带着 discrepancy 说明交付，
   不把 6 小时烧在一个错路径上。

## 结构

```
submission.yaml        name / model_api / install / serve / env
serve.py               一连接一任务；读 task 帧、起决策循环、处理 cancel、发 done
skillkit/
  harness.py           决策循环 + system prompt 装配 + 守卫熔断
skillkit/
  specgen.py           交付合同自动抽取
  router.py            instruction → 领域 / 文档族 / skill 上下文
  guard.py            把 validate.py + spec.json 推进容器执行并解析结果
  transport.py         WSTransport（协议）/ LocalTransport（离线 dryrun）
  model.py             模型客户端：OpenAI 兼容 + Anthropic 原生（cache_control）
dryrun.py              无 Docker、无 key 的离线自测（含"守卫拒绝→修复→通过"路径）
skills/
  _shared/             SKILL.md（五件套 / 约束台账 / 收尾三段式）+ validate.py（守卫）
  electrical/ structural/ mep/ civil/ misc/  各领域 SKILL.md + checklist.md（通用格式惯例，无 dev 题指纹）
requirements.txt       websockets==15.0.1  httpx==0.28.1
criteria.py            可执行验收判据（GATE-A 本地 / GATE-D 数据 / GATE-B 可提交）
devtools/f01_check.py  F-01 静态合规自检（已接入 criteria.py 的 G-12）
GOAL.md                目标、里程碑、硬约束、非目标
docs/                  交接评估、修复记录、F-01 合规说明
writeups/              5 篇技术叙事：为什么是这个形状、踩过的坑、还没证明的部分
```

## 三项指标（对 baseline artifacts 的离线静态回归，非本 harness 实测）

| 环节 | 结果 | 说明 |
|---|---|---|
| specgen 路径解析 | **25 / 29** | 4 道短题（offset / footing / solar×2）题面完全不写路径，转成 `confidence=low`，由模型读 task.md 与 house 模板自行确立 |
| specgen 结构抽取 | zip 型抽出 CSV 列头、必需成员、`### N.` 文件清单 | 某电缆选型题的 `wire_schedule.csv` 列头可完整还原 |
| router 领域判定 | **23 / 29** | 错分多为"该题本身就是跨专业"；`_shared` 始终加载，不致命 |
| guard 对 baseline 真实产出 | **17 PASS / 2 WARN / 5 FAIL / 3 no-path**（共 27 题有产出） | 5 个 FAIL 中有 1 个是 baseline 真的漏交了题面要求的 `instruction_to_engineer.md`；其余是 baseline 落在与题面不同的位置上——这正是守卫要抓的东西 |

一道电缆选型题的 baseline 真实产物经自动合同判定 PASS（zip 成员齐全、CSV 列头与嵌套表格可解析）。

## 本地怎么跑

```bash
# 1) 不用 Docker、不用 key：验证协议、循环、守卫拒绝→修复→通过
python3 dryrun.py

# 2) 用真实题面 + 真实 workdir，仍然用 stub 模型
python3 dryrun.py --artifact /path/to/artifacts/<task> --instruction inst.txt

# 3) 本地模拟原生 Claude API，验证模型请求、WebSocket 与交付闭环
python3 devtools/protocol_smoke.py

# 4) 可执行验收判据（缺 29 题数据时应报 BLOCKED，而不是 PASS）
python3 criteria.py

# 5) 真模型（本地起服务，自己当 evaluator）
export MODEL_BASE_URL=https://api.example.com/v1 MODEL_API_KEY=... MODEL_NAME=...
PORT=8080 python3 serve.py
```

官方链路（需要 Docker + uv + harbor）：

```bash
export PLE_ENTRY_DIR="$PWD"      # 评测当前 WSL/Linux 仓库
bash devtools/wsl-run.sh check    # 快速检查，含 cancel
bash devtools/wsl-run.sh pilot    # 默认单题，结果留在官方 kit 的 runs/ 下
bash devtools/wsl-run.sh dev      # 全量 29 题，生成参赛 artifacts/
# 复核后将 artifacts/ 与 harness 提交到同一 Git commit
bash devtools/wsl-run.sh ready    # 校验产物、重判、完整 kit check
```

## 已知缺口（v1 边界）

1. **4 道题无路径**：specgen 只能给出 `confidence=low`，靠模型首轮 `cat task.md` 后自建。
   更稳的做法是把 task.md 全文回灌 specgen 重解析（harness 已实现这一步，但 task.md 若不在
   workdir 根目录就失效）。
2. **守卫是结构性的**：只查路径、可解析性、列头、必需件，不判断工程内容对不对。
3. **CSV 列头硬判**：若题面列头与 grader 实际接受的有偏差，会误判（已由 3 次熔断兜底）。
4. **正式开发题评分**需要云端运行器获得 Hugging Face 题集读取权。已用真实 Gemma 模型完成官方 kit 合成任务和独立工程算例。[运行记录](docs/03-validation-methods.md)
5. **模型选择**由 `submission.yaml` 声明，当前参赛配置为 `google-cloud/glm-5.2`。云端开发流程支持 GPT-6.1 Sol 和 HF 模型，使用本地量化 Gemma 时对适用的小型多文件任务启用首轮直接生成 Python。

## 下一步（按收益排序）

1. 在能跑 Docker 的机器上 `kit check`，修 listen/smoke 两个阶段，这是提交的前提。
2. 用真模型跑 1~2 道 dev 题，校准 system prompt 的步数节奏（现在"第 10~20 步落第一版"
   是推断值，需要实测确认）。
3. specgen 的 4 道 no-path 题：改为"首轮 exec 读全 task.md 后重解析"，并把 house 模板
   文件名规则写进对应 skill。
4. 把 guard 的 `zip_soft` 从 WARN 提升为按题面措辞决定的硬判（现在一律 soft）。

> 以上是按「提分」排序的原始设想；**提交前的真实优先级（合规清理 → kit check → 真模型 → dev set → 同一 commit 提交）以 [HANDOFF.md](HANDOFF.md) 为准**。WSL2 侧的一键流程在 `devtools/wsl-run.sh`。

## writeups

`writeups/` 下是 5 篇，按顺序读：

| # | 篇目 | 主题 |
|---|---|---|
| 00 | [交付物就是分数](writeups/00-why-this-shape.md) | 从 84 步与 96% cached 两个数字反推出"合同先行" |
| 01 | [spec-first](writeups/01-spec-first.md) | 题面两种结构、两个正则坑（14→0→25） |
| 02 | [守卫](writeups/02-guard.md) | 只查结构为什么够、命名空间双括号 bug、硬软分离、熔断 |
| 03 | [路由](writeups/03-routing.md) | 合规启发式 vs 题面指纹的红线，20→23，以及 domain/subdomain 拆分 |
| 04 | [成本与时钟](writeups/04-cost-and-clock.md) | cache_control、6 小时预算、提前收工 |
