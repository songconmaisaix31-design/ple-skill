# PLE 实验接续记录

## H/I 已完成：停止源码片段候选

六个整对、十二个实验臂均可独立复评。基线与候选宏平均分都是 `0.0`，三次重复的配对差全为 `0.0`，配对差样本方差为 `0.0`。候选 6/6 实际收到正确源码片段，基线 0/6；两臂的修复请求完成率均为 0/6，均未在第 395 秒前交付文件。按预登记门槛判定 `stop_candidate_no_gain`，保留现行 `text` 首轮 Python 策略。[完整报告、图表和证据](controlled-repair-replay-v1/README.md)

最终补齐运行是 [GitHub Actions 45247679226](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45247679226)，运行提交为 [`de4be676`](https://github.com/songconmaisaix31-design/ple-skill/tree/de4be67625116a599f8c5d39d3eb10ed117db03c)。两组共用第 250 秒释放的失败首答，第 395 秒读取实际交付文件；模型、提示词、种子、配对顺序、输入和评分器均未改变。只对账户无关的模型下载器加入 HTTP/1.1、断点续传和全错误重试，修复已观察到的 9.92 GB GGUF 传输中断。

该运行的首次 H1 作业在 40 分钟上限被取消且没有上传工件；同一运行中的另外五个整对均已成功归档。只对 H1 使用 GitHub 的单作业重跑 [137973972058](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45247679226/job/137973972058)，仍使用 `de4be676` 和完全相同的配对设置。其他整对不重跑。主分析按第一份完整有效整对固定：I3 使用较早运行 `45246424026` 的工件，H3、I1、I2、H2 使用当前运行首次尝试的工件，H1 使用技术补跑工件。

无效尝试按时间保留，不进入分数分析：

- [45245652599](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45245652599)，提交 `5ff7fbf5`：独立实验分支缺少协议指定的历史 D 证据包，六组在模型加载前由正负对照终止，无推理、无分数。
- [45245913028](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45245913028)，提交 `9fcdb2b8`：证据包及离线链通过，但记录器仍按旧 F/G 协议读取 `split.cases`，触发 `KeyError: cases`；缺少合格的整对记录，结果不进入分析。
- [45246424026](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45246424026)，提交 `55a02ad1`：四个早结束整对在 `model_start` 阶段失败，`startup.log` 一致显示 Hugging Face 下载的 HTTP/2 流被 `CANCEL`；I3 后来形成第一份完整有效整对并按预先固定的时间优先规则进入主分析。

下载可靠性提交 [`c3d73111`](https://github.com/songconmaisaix31-design/ple-skill/commit/c3d73111cd1f90ae57fb3e9fdef27c23152989e8) 因普通 push 另触发了 [45247632095](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45247632095)。它不是 H/I 配对矩阵，不进入本实验，也不作为分数证据。

在第一份完成的 I3 原始工件上运行独立校验器时，发现 H/I 记录器把局部变量 `first` 从预登记的首臂名称覆盖成了“唯一脚本首答记录”数组，导致冗余的 `first_mode` 字段类型错误。该变量覆盖发生在两臂实验和 395 秒取样结束之后，不改变模型请求、返回代码、交付文件、顺序或分数。为避免根据已出现的结果决定是否重跑，在当前六组结束前冻结证据修复规则：原始 Actions 工件保持不变并单独归档；只有当错误字段逐字等于同一臂 `model-io.jsonl` 中唯一的 `call=1, scripted=true` 响应时，派生分析包才按协议的 `design.first_arm` 重建该字段，并记录修复前后 SHA-256。条件不满足的臂一律判无效，其他字段不做修补。该规则只恢复可由原始记录独立证明的分配元数据。

## F/G 已完成，保留首轮 Python 基线

第 395 秒，F/G 六个同机配对的两臂均拿到满分。三次跨题平均分差均为 0，配对差样本方差为 0。六次候选都在首轮成功，实际源码反馈曝光 0/6。根据冻结协议，关于修复提示是否有益的证据不足。保留现有首轮 Python 策略，F/G 转入开发数据。[实验报告及逐次交付](repair-source-v1/README.md) · [F/G 运行](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45232669702)

G3 候选在首次尝试中未启动模型，评分缺测，同机基线为 1。第 2 次仅重跑 G3，两个实验臂都在同一台新机器上执行。主分析使用第一份有效的整对结果；首轮的孤立基线只列在尝试记录中。[首次尝试](repair-source-v1/attempts/attempt-1.json) · [G3 补跑](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45232669702/job/137913411809)

## 已完成设计：在已知会失败的首轮程序上测量修复效果

| 项目 | 冻结的比较 |
|---|---|
| 问题 | 两组确实遇到相同 Python 异常时，附上出错行及其上下文，能否使模型在规定时间内交出可评分的文件？ |
| 数据、起点 | A–G 为开发数据。H/I 是两份新输入，共用来自历史 D 首轮的真实模型程序。统一去掉注释，保留 AST 和行号，避免候选从原注释直接看到修复提示。两组均真实执行并从相同的第 81 行 TypeError 开始。评分器及正确修补留在宿主。 |
| 基线、唯一变量 | 基线收到现行异常反馈；候选只在该消息末尾附上出错行及上下各两行，含行号，最多 800 字符。两组接下来的修复都调用同一个云端运行的 Gemma 4 26B A4B。 |
| 时间和配对 | 参照旧 D 三次首答耗时，统一在任务开始后第 250 秒释放共同首答，第 395 秒对实际文件取样，名义预算 720 秒。每题三个同机配对，温度 0、种子 17，重启服务，交替顺序。 |
| 继续门槛 | 6 对全部可评分、候选 6/6 确认收到正确片段、基线 0/6 收到片段。满足上述前提后，三个重复的跨题平均分差都大于 0、且 H/I 各自平均分差都非负，才转到有自然失败的新题复验。测量完整但收益不足则停止该候选；缺测或反馈未送达则证据不足。 |
| 输出 | 独立重评截止时的文件；记录真实修复请求、完整返回代码、未完成请求、文件完整性、每组得分和配对差、三次重复的均值及样本方差。结果仅说明指定故障下的恢复能力。 |

H/I 已通过离线正负对照。两题以错误程序运行时均无交付、得 0，一处相同表达式修正后均得 1。对照只验证输入、故障与评分链。[冻结协议、数据和哈希](controlled-repair-replay-v1/protocol.json) · [逐臂结果](controlled-repair-replay-v1/trials.csv) · [独立证据](controlled-repair-replay-v1/evidence.zip)

设计参考：Chen 等人在 Self-Debugging 中让语言模型利用代码执行结果修正程序。这里把问题进一步收窄，给两组同一个真实故障和相同剩余时间，单独测量五行源码对交付的影响。[ICLR 2024 论文](https://proceedings.iclr.cc/paper_files/paper/2024/hash/2460396f2d0d421885997dd1612ac56b-Abstract-Conference.html)

## 下一轮：受约束局部补丁接口

| 项目 | 预登记方向 |
|---|---|
| 问题 | 完整程序修复在剩余 145 秒内 0/12 返回。把修复动作缩成一个受约束的局部行替换，能否在同一截止时间形成实际交付？ |
| 数据 | A–I 全部转入开发数据。新建 J/K 两份未见输入，继续使用同一个可验证失败程序与第 81 行 TypeError；先冻结输入哈希、正负对照和补丁宿主校验器。 |
| 基线 | 双方都收到相同的五行源码。基线维持当前完整程序重写响应。 |
| 唯一模块 | 候选只返回机器可解析的单行替换；宿主严格检查行号、语法和允许的单行变更后，把补丁应用到相同失败程序并执行。不给参考修补、目标成本或输出文件。 |
| 固定项 | Gemma 4 26B A4B、温度 0、种子 17、第 250 秒释放、第 395 秒文件快照、720 秒名义预算、每题 3 次同机配对并交替顺序。 |
| 主指标 | 第 395 秒独立文件分数和配对差；并列报告响应完成率、补丁解析/应用/执行成功率和首个可执行补丁延迟。正式 PLE 与原创诊断继续分开。 |
| 继续门槛 | 六对全部可评分，候选 6/6 走过已登记的补丁接口且无越权改动；三个重复的跨题宏配对差都严格大于 0，J/K 各自平均差非负。否则停止补丁模块；缺测则只补跑失败整对。 |

这一轮只改变修复动作接口，依据 SWE-agent 的受约束编辑 ACI 和 Agentless 的定位—补丁—验证分解。先完成协议、J/K 数据和离线传输正负对照，再启动模型实验。[SWE-agent 论文](https://papers.nips.cc/paper_files/paper/2024/hash/5a7c947568c1b1328ccc5230172e1e7c-Abstract-Conference.html) · [Agentless 论文](https://arxiv.org/abs/2407.01489)

## 正式 PLE 开发集

正式题最近一次运行在获取受限数据前收到 Hugging Face OIDC 的 `invalid_grant`，评分步骤跳过。当前未取得正式开发集得分。正式成绩单列，保留对应的模型、官方任务、评分器及运行证据。[正式题运行](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45204574378/job/137796706042) · [官方数据集](https://huggingface.co/datasets/google/physical-engineerings-last-exam)

