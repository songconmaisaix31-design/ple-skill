# PLE harness — writeups

Physical-Engineering's Last Exam（PLE），Google 赞助，2026-11-09 → 2027-01-05。
提交物是一个 GitHub commit：`submission.yaml` + `serve.py` + 同 commit 的 `artifacts/`。
每题一个容器、一条 WebSocket、6 小时、2 CPU / 4GB。

这组 writeup 记录的是**这个 harness 为什么长成这样**，不是功能清单。
顺序建议按 00 → 04 读。

| # | 篇目 | 一句话 |
|---|---|---|
| [00](00-why-this-shape.md) | 交付物就是分数 | 为什么我把顺序反过来：先写验收合同，再让模型说话 |
| [01](01-spec-first.md) | spec-first | 从题面里把"交什么、交到哪、列头是什么"抽出来，以及我踩的两个正则坑 |
| [02](02-guard.md) | 守卫 | 只做结构性检查为什么就够，以及它抓到 baseline 漏交的那一次 |
| [03](03-routing.md) | 路由 | 领域词表 vs 题面指纹：什么是合规启发式，什么会被判作弊 |
| [04](04-cost-and-clock.md) | 成本与时钟 | 96% 的 prompt token 是 cached，不显式打标记就是每轮全价 |

---

## 00 — 交付物就是分数

先说一个把我打醒的数字：**baseline 在 dev set 上的平均轨迹是 84 步**。

29 道题、2441 步，平均 84。而官方指南里明写"高分 harness 会读完整题面、检查起始文件、
小步验证、**尽早写出一版交付物再迭代**"。84 步意味着这个"尽早"不是第 60 步，是第 15 到 25 步。
换句话说：**大部分 agent 的步数，花在了"我以为交付物该叫什么、该放哪"这种本该零成本的事情上。**

第二个数字更直接：29 题的交付物类型分布是 16 docx / 11 zip / 1 xlsx / 1 ifc / 1 pdf / 2 py / 1 eml。
评分规则写着"grader 检查交付物的精确路径、文件名、格式、内容，占绝大多数分"。

把这两件事放一起，结论很冷：**这不是一个"谁的工程判断更强"的比赛，是一个"谁不会在格式上白给"的比赛。**
结构力学算得再对，交成 `output/report.docx` 而题面要 `Thelbridge_Verification_Memo_Item048_BlockB.docx`，
就是零分。

### 我最初想错的地方

我第一版的设计是照人类工程流程切的：读图 → 查规范 → 算 → 起草 → 审 → 改。
听起来很专业，实际是错的，因为它默认"过程正确 → 结果正确"。但这个比赛的评分只看结果，
而且**过程里每一步都在烧 6 小时里的一格电**。

后来定了现在的顺序，一句话概括：**在模型开口之前，先把验收合同写出来。**

1. `specgen` 从 instruction（必要时叠加 `task.md`）抽出交付路径、模式、必需成员、CSV 列头，落盘成 `spec.json`
2. `router` 把题面路由到领域 skill（structural / electrical / mep / civil / misc），拿到该领域的文档骨架
3. 这两样东西拼进 system prompt，作为"最高权威"，排在所有工程指导之前
4. 第 10~20 步落第一版**能打开**的完整包，然后原地重写
5. `guard` 每 2 步在容器里跑一次 `validate.py`；`finish` 时不过就直接拒绝

第 5 条是整个系统里我最在意的部分：**模型不能自己宣布完工。** 它必须拿到守卫的通行证。

### 三个数字（都在 29 道真实 dev 题上量的）

| 环节 | 结果 |
|---|---|
| specgen 路径解析 | 25 / 29 |
| router 细领域判定 | 23 / 29 |
| guard 对 baseline 真实产出 | 19 / 24 PASS 或 WARN |

最后一个数字值得单独说。我拿 baseline 已经产出的交付物去喂我的守卫，19 个通过，5 个不过。
其中 4 个是 baseline 把东西放在了和题面不同的位置——这说明守卫在抓真问题。
第 5 个更有意思：`frame-extension-method` 的题面用 `### N. \`file\`` 列了 7 个文件，
baseline 的 zip 里只有 6 个，少的那个是 `instruction_to_engineer.md`。

**一个已经跑完、看起来交了活的 agent，漏了题面明确要求的一个文件。** 没有人会发现，除了守卫。

### 我还没证明的部分

诚实的边界：这台机器没有 Docker，也没有模型 key。

- `kit check` 的 `listen` / `smoke` 两关没跑过
- `serve.py` 的真实端到端没跑过（协议帧、cancel、usage 上报都按 AGENTS.md §7 逐条实现，但没真跑过不算数）
- "第 10~20 步落第一版" 是从 84 步反推的推断值，需要用真模型校准

所以现在这个仓库的状态是：**代码层自洽（`criteria.py` 的 GATE-A 10/10），但还不能提交（GATE-B 0/7）。**
我把这个状态写进 `GOAL.md` 而不是含糊过去，因为 3 次提交机会，一次 build 失败就终止。
