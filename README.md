# PLE harness — v1 (runs the dev set)

Physical-Engineering's Last Exam 参赛 harness。第一版，可实际在 dev set 上跑。

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
  electrical/ structural/ mep/ civil/ misc/  各领域 SKILL.md + checklist.md（29 题全覆盖）
requirements.txt       websockets==15.0.1  httpx==0.28.1
criteria.py            可执行验收判据（GATE-A 本地 / GATE-B 可提交）
GOAL.md                目标、里程碑、硬约束、非目标
writeups/              5 篇技术叙事：为什么是这个形状、踩过的坑、还没证明的部分
```

## 三项指标（都在 29 道真实 dev 题上量过）

| 环节 | 结果 | 说明 |
|---|---|---|
| specgen 路径解析 | **25 / 29** | 4 道短题（offset / footing / solar×2）题面完全不写路径，转成 `confidence=low`，由模型读 task.md 与 house 模板自行确立 |
| specgen 结构抽取 | zip 型抽出 27 列 CSV 头、必需成员、`### N.` 文件清单 | `lv-cable-sizing` 的 `wire_schedule.csv` 28 列可完整还原 |
| router 领域判定 | **23 / 29** | 错分多为"该题本身就是跨专业"；`_shared` 始终加载，不致命 |
| guard 对 baseline 真实产出 | **17 PASS / 2 WARN / 5 FAIL / 3 no-path**（共 27 题有产出） | 5 个 FAIL 中有 1 个是 baseline 真的漏交了题面要求的 `instruction_to_engineer.md`；其余是 baseline 落在与题面不同的位置上——这正是守卫要抓的东西 |

`lv-cable-sizing` 的真实产物经自动合同判定 PASS（5 项 zip 成员、27 列列头、2 个嵌套 xlsx 可解析）。

## 本地怎么跑

```bash
# 1) 不用 Docker、不用 key：验证协议、循环、守卫拒绝→修复→通过
python3 dryrun.py

# 2) 用真实题面 + 真实 workdir，仍然用 stub 模型
python3 dryrun.py --artifact /path/to/artifacts/<task> --instruction inst.txt

# 3) 真模型（本地起服务，自己当 evaluator）
export MODEL_BASE_URL=https://api.example.com/v1 MODEL_API_KEY=sk-... MODEL_NAME=...
PORT=8080 python3 serve.py
```

官方链路（需要 Docker + uv + harbor）：

```bash
uv run python -m kit check /path/to/this/repo --cancel-test
uv run python eval/run.py /path/to/this/repo     # 写 artifacts/，必须与代码同一 commit
uv run python -m kit artifacts /path/to/this/repo
```

## 已知缺口（v1 边界）

1. **4 道题无路径**：specgen 只能给出 `confidence=low`，靠模型首轮 `cat task.md` 后自建。
   更稳的做法是把 task.md 全文回灌 specgen 重解析（harness 已实现这一步，但 task.md 若不在
   workdir 根目录就失效）。
2. **守卫是结构性的**：只查路径、可解析性、列头、必需件，不判断工程内容对不对。
3. **CSV 列头硬判**：若题面列头与 grader 实际接受的有偏差，会误判（已由 3 次熔断兜底）。
4. **未跑过真模型**：本地无 Docker、无 API key，`serve.py` 的真实端到端尚未验证；
   协议帧格式、cancel、usage 上报按 `AGENTS.md` §7 逐条实现，但需要一次真跑才算数。
5. **模型选择**：`submission.yaml` 现填 `google-cloud/claude-opus-5-5`。Claude 走
   Anthropic 原生路径并显式打 `cache_control`（system + 最新消息），因为 dev 轨迹里
   96% 的 prompt token 是 cached——不打就是每轮全价重付。

## 下一步（按收益排序）

1. 在能跑 Docker 的机器上 `kit check`，修 listen/smoke 两个阶段，这是提交的前提。
2. 用真模型跑 1~2 道 dev 题，校准 system prompt 的步数节奏（现在"第 10~20 步落第一版"
   是推断值，需要实测确认）。
3. specgen 的 4 道 no-path 题：改为"首轮 exec 读全 task.md 后重解析"，并把 house 模板
   文件名规则写进对应 skill。
4. 把 guard 的 `zip_soft` 从 WARN 提升为按题面措辞决定的硬判（现在一律 soft）。

## writeups

`writeups/` 下是 5 篇，按顺序读：

| # | 篇目 | 主题 |
|---|---|---|
| 00 | [交付物就是分数](writeups/00-why-this-shape.md) | 从 84 步与 96% cached 两个数字反推出"合同先行" |
| 01 | [spec-first](writeups/01-spec-first.md) | 题面两种结构、两个正则坑（14→0→25） |
| 02 | [守卫](writeups/02-guard.md) | 只查结构为什么够、命名空间双括号 bug、硬软分离、熔断 |
| 03 | [路由](writeups/03-routing.md) | 合规启发式 vs 题面指纹的红线，20→23，以及 domain/subdomain 拆分 |
| 04 | [成本与时钟](writeups/04-cost-and-clock.md) | cache_control、6 小时预算、提前收工 |
