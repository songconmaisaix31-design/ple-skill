# PLE 实验接续记录

## H/I 受控修复实验正在执行

当前冻结重跑是 [GitHub Actions 45247679226](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45247679226)，运行提交为 [`de4be676`](https://github.com/songconmaisaix31-design/ple-skill/tree/de4be67625116a599f8c5d39d3eb10ed117db03c)。两组仍共用第 250 秒释放的失败首答，第 395 秒读取实际交付文件；模型、提示词、种子、配对顺序、输入和评分器均未改变。只对账户无关的模型下载器加入 HTTP/1.1、断点续传和全错误重试，修复已观察到的 9.92 GB GGUF 传输中断。接续时只轮询该运行及下面较早运行中尚未结束的整对，不再另开运行。

无效尝试按时间保留，不进入分数分析：

- [45245652599](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45245652599)，提交 `5ff7fbf5`：独立实验分支缺少协议指定的历史 D 证据包，六组在模型加载前由正负对照终止，无推理、无分数。
- [45245913028](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45245913028)，提交 `9fcdb2b8`：证据包及离线链通过，但记录器仍按旧 F/G 协议读取 `split.cases`，触发 `KeyError: cases`；缺少合格的整对记录，结果不进入分析。
- [45246424026](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45246424026)，提交 `55a02ad1`：记录器协议兼容已修复。已结束的整对都在 `model_start` 阶段失败，`startup.log` 一致显示 Hugging Face 下载的 HTTP/2 流被 `CANCEL`，没有实验观测。若该运行中较晚结束的某整对形成完整、可独立复评的记录，仍按时间优先使用该整对；失败整对使用当前冻结重跑中的第一份有效记录。

下载可靠性提交 [`c3d73111`](https://github.com/songconmaisaix31-design/ple-skill/commit/c3d73111cd1f90ae57fb3e9fdef27c23152989e8) 因普通 push 另触发了 [45247632095](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45247632095)。它不是 H/I 配对矩阵，不进入本实验，也不作为分数证据。

## F/G 已完成，保留首轮 Python 基线

第 395 秒，F/G 六个同机配对的两臂均拿到满分。三次跨题平均分差均为 0，配对差样本方差为 0。六次候选都在首轮成功，实际源码反馈曝光 0/6。根据冻结协议，关于修复提示是否有益的证据不足。保留现有首轮 Python 策略，F/G 转入开发数据。[实验报告及逐次交付](repair-source-v1/README.md) · [F/G 运行](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45232669702)

G3 候选在首次尝试中未启动模型，评分缺测，同机基线为 1。第 2 次仅重跑 G3，两个实验臂都在同一台新机器上执行。主分析使用第一份有效的整对结果；首轮的孤立基线只列在尝试记录中。[首次尝试](repair-source-v1/attempts/attempt-1.json) · [G3 补跑](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45232669702/job/137913411809)

## 下一轮：在已知会失败的首轮程序上测量修复效果

| 项目 | 冻结的比较 |
|---|---|
| 问题 | 两组确实遇到相同 Python 异常时，附上出错行及其上下文，能否使模型在规定时间内交出可评分的文件？ |
| 数据、起点 | A–G 为开发数据。H/I 是两份新输入，共用来自历史 D 首轮的真实模型程序。统一去掉注释，保留 AST 和行号，避免候选从原注释直接看到修复提示。两组均真实执行并从相同的第 81 行 TypeError 开始。评分器及正确修补留在宿主。 |
| 基线、唯一变量 | 基线收到现行异常反馈；候选只在该消息末尾附上出错行及上下各两行，含行号，最多 800 字符。两组接下来的修复都调用同一个云端运行的 Gemma 4 26B A4B。 |
| 时间和配对 | 参照旧 D 三次首答耗时，统一在任务开始后第 250 秒释放共同首答，第 395 秒对实际文件取样，名义预算 720 秒。每题三个同机配对，温度 0、种子 17，重启服务，交替顺序。 |
| 继续门槛 | 6 对全部可评分、候选 6/6 确认收到正确片段、基线 0/6 收到片段。满足上述前提后，三个重复的跨题平均分差都大于 0、且 H/I 各自平均分差都非负，才转到有自然失败的新题复验。测量完整但收益不足则停止该候选；缺测或反馈未送达则证据不足。 |
| 输出 | 独立重评截止时的文件；记录真实修复请求、完整返回代码、未完成请求、文件完整性、每组得分和配对差、三次重复的均值及样本方差。结果仅说明指定故障下的恢复能力。 |

H/I 已通过离线正负对照。两题以错误程序运行时均无交付、得 0，一处相同表达式修正后均得 1。对照只验证输入、故障与评分链。接续时先核对当前 PR 及云端运行；若未启动 H/I，在独立实验分支实现首答的定时回放与曝光校验，用实际任务包装器验证正负对照，固定运行和评分代码提交后再启动六个配对。先写入 run ID，之后沿用已有运行。[冻结协议、数据和哈希](controlled-repair-replay-v1/protocol.json) · [离线验证](../../devtools/verify_repair_fixture.py)

设计参考：Chen 等人在 Self-Debugging 中让语言模型利用代码执行结果修正程序。这里把问题进一步收窄，给两组同一个真实故障和相同剩余时间，单独测量五行源码对交付的影响。[ICLR 2024 论文](https://proceedings.iclr.cc/paper_files/paper/2024/hash/2460396f2d0d421885997dd1612ac56b-Abstract-Conference.html)

## 正式 PLE 开发集

正式题最近一次运行在获取受限数据前收到 Hugging Face OIDC 的 `invalid_grant`，评分步骤跳过。当前未取得正式开发集得分。正式成绩单列，保留对应的模型、官方任务、评分器及运行证据。[正式题运行](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45204574378/job/137796706042) · [官方数据集](https://huggingface.co/datasets/google/physical-engineerings-last-exam)

