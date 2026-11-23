# 工程交付物如何验证

2026-11-23。以下实验使用原创数据，并单独记录正式 PLE 开发题的运行状态。

## 先判可行，再比目标值

PLE 论文对 86 种模型和 harness 组合做了失败分析。在零分运行中，25.3% 没有可评分的交付物，70.4% 交出了被评为零分的文件。最强组合在共同创作题目上平均满足 91% 的约束，但只有 41.3% 的交付项满足全部硬约束并获得目标函数得分。工程验证应同时覆盖文件交付、数值可行性和可行方案的质量。[论文 §5.3](https://arxiv.org/pdf/2610.30537)

开源 SWE-agent 把编辑后的局部反馈交给模型。PLE 的 plan-verify 示例让 verifier 在全新上下文读取实际文件，并为返工预留时间。本项目把路径、格式、列头等可机械判断的要求交给程序核验，在模型时间耗尽时只报告有文件证据的状态。对于成本等可计算目标，参考 PAL 的方法，让模型编写计算程序，另用独立实现复算提交值。[SWE-agent](https://papers.nips.cc/paper_files/paper/2024/hash/5a7c947568c1b1328ccc5230172e1e7c-Abstract-Conference.html) · [PLE plan-verify 示例](https://github.com/google-research/ple/tree/8320f0402fdca9f42476607f72bcfd5271cd50c9/sample_submissions/plan-verify) · [PAL](https://proceedings.mlr.press/v202/gao23f.html)

## 三项可复现实验

| 实验 | 独立判据 | 观察指标 |
|---|---|---|
| 文件验收 | 5 种原创交付场景，预先标注 8 份有效交付和 18 份无效交付。同一批文件交给两个版本的解析器和校验器 | 误收、误拒以及校验器异常分别计数 |
| 时间耗尽 | 可控模型先落盘再停止响应，也注入缺件、覆盖、取消和写入被打断等情形 | 最终消息能否区分已验证、检查失败和状态未知 |
| 两个调度算例 | 六时段的教学水箱。独立评分器重算每期守恒、上下限、泵量、终态与费用，再穷举可行策略 | 可行性、提交成本、最优成本、运行时间分别报告。不可行时计零 |

在固定的 26 个样本中，旧版正确判定 10 个，其中误收 14 个、误拒 2 个。候选版正确判定 26 个，8 份有效交付和 18 份无效交付全部判对。截止时间回归覆盖 9 种情况。旧版在已写文件和未写文件时会返回相同的超时说明，候选能根据最后一次有效检查报告状态。这些数字分别衡量文件判断与恢复行为。

文件验收对照的基线为 `b0c2ece7c6e4069c64c411bb39ebf65f20791a36`。新场景涵盖目录交付、分散文件、压缩包、单份 Word 函件和单独 CSV。用正确文件与近似但错误的文件成对检查，避免靠一律判失败来抬高错误检出率。

```sh
python devtools/artifact_regression.py --baseline /path/to/baseline-checkout --verbose
python devtools/deadline_regression.py
python devtools/design_regression.py --prepare /tmp/storage-a --variant a
# 用待测模型读取 /tmp/storage-a/task.md 和两份输入，写入 output/ 后再独立评分
python devtools/design_regression.py --grade /tmp/storage-a --variant a
```

GPT-6.1 Sol 在独立会话中只获得题面和输入，使用自行编写的计算程序。两个算例都提交了 CSV 时序和 JSON 汇总。A 的六期泵量为 4、2、2、4、0、4，总成本 92 美分。B 的六期泵量为 3、1、3、3、0、5，总成本 67 美分。独立评分器复算后，两者均可行且达到各自的全局最低成本。这是原生模型会话的结果。云端 Gemma 实验另外经过本仓库的 serve 入口、官方 WebSocket relay 和隔离的 Docker 工作区。

### 云端模型对照

四组运行都使用相同的 Gemma 4 26B A4B 量化权重、固定的 llama.cpp 构建、四核 CPU、零温度和相同的独立评分器。每个算例每组各运行一次，指定 720 秒的任务预算。工具、评分和模型不会读取枚举器的最优答案。评分器要求从容器导出的交付能组成恰含指定 CSV 和 JSON 的目录，然后才核对物理量和成本。

| 版本 | 算例 A | 算例 B | 累计输入 token（A / B） |
|---|---|---|---|
| 旧验收逻辑 | 0 | 0 | 17,030 / 17,022 |
| 增加截止前复核和文件校验 | 0 | 0 | 17,128 / 17,099 |
| 完整识别 Markdown 列出的两个输出 | 0 | 0 | 17,243 / 17,132 |
| 同一版本启用短提示、预读小输入并建议一次计算写出多文件 | 0 | 0 | 4,129 / 3,848 |

各次评分均停在两份文件的交付要求，未产生可比较的 Gemma 方案成本。最后两组是一次成对的任务接口实验，累计输入分别减少 76.1% 和 77.5%，可行解数量都是 0/2。日志没有逐文件导出诊断，无法单凭这个分数判断具体是哪份文件缺失、目录有额外文件，还是文件类型或大小不符合导出条件。保留完整的交付物校验，精简提示分支只作为实验记录。两个算例不足以推断这种提示对其余 PLE 任务的效果。[原始基线](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45186150004) · [首次验收更新](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45186679285) · [完整校验对照](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45187585218) · [短提示实验](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45189005262)

### 独立核对最优下界

另外只读取两张输入表，使用 SciPy 1.17.0 的 HiGHS 混合整数求解器重新建模。每个时段为允许的泵量建一个二元变量，各时段恰选一个。每个前缀的累计泵量减累计需求加初始库存必须处于库存上下限，最后一期再加终态限制。目标函数为各期泵量乘费率之和。A 和 B 的可行目标值和求解器给出的下界分别同为 92 和 67 美分，两次相对最优间隙均为零。[SciPy MILP 接口](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html)

新增的 C 在两个时段停泵，并要求期末库存恰好为 2。云端对照开始前，分别用动态规划、穷举和 HiGHS 核对了最低成本 35 美分。动态规划给出 16 条可行路径，其中仅 1 条最优。任务容器只接收题面和两份输入，独立评分器在容器外运行。

### 首次 Python 调用对照

CodeAct 将可执行的 Python 和程序运行反馈用于多步任务。Hugging Face 的 smolagents 实现了文本代码动作，mini-SWE-agent 的 v2 默认使用原生工具调用。本实验比较三种策略：沿用短提示的工具循环、首轮强制调用原生 `run_python`、首轮直接生成完整 Python。后两种使用相同的输入、生成上限和任务隔离环境，执行结果再交给原工具循环。每题每组一次，统一使用零温度、种子 17、720 秒预算和相同的评分器。[CodeAct 论文](https://proceedings.mlr.press/v235/wang24h.html) · [smolagents](https://github.com/huggingface/smolagents/blob/main/src/smolagents/agents.py) · [mini-SWE-agent](https://mini-swe-agent.com/latest/advanced/v2_migration/) · [云端对照](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45204343520)

每个 runner 先用固定的两份测试文件经过正式 kit 的 WebSocket、Docker 工作区和文件导出路径，逐字节核对内容。随后新建任务容器运行模型，分别记录模型请求是否被中断、工具是否成功执行、最终目录中两个文件的类型与大小。文件通过结构检查后，评分器复算六个时段的库存、约束和成本。

| Gemma 4 26B A4B 策略 | A 最终成本 | B 最终成本 | C 最终成本 | 首轮程序通过结构检查的秒数（A / B / C） |
|---|---:|---:|---:|---|
| 原短提示工具循环 | 92 | 未交付 | 35 | 原流程无同口径事件 |
| 首轮原生 Python 工具调用 | 92 | 67 | 35 | 216 / 267 / 265 |
| 首轮直接生成 Python | 92 | 67 | 35 | 241 / 246 / 245 |

单位为美分。每个已交付的方案均经独立评分确认达到最优。B 的原流程两次 Python 执行都以退出码 1 结束，第三次推理在时间耗尽时被中断。终态容器中没有 `output/`，根目录也没有两份同名文件。9 个运行器的文件传输自检均通过。每个算例和策略只运行一次；两种首轮 Python 策略的速度排序随算例变化。此前的短提示运行在 A、B 均未交付，说明单次运行的结果会波动。[九组完整日志](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45204343520)

PR 里的 `PLE_CODE_ACTION=text` 开启文本 Python 首轮，`PLE_CODE_ACTION=native` 在 Chat Completions 接口启用原生工具首轮。未配置时使用原参赛流程。仅当任务明确列出 2–3 个文本输出、同时有少量可完整读取的命名文本输入，且没有 MCP 或附加文档依赖时，才使用新策略。模型代码通过同一任务容器执行；无效、截断或报错的首轮可回退常规工具，后续仍要核实工程结果。

第一轮结束后，另开九个独立运行器检验提前交付。三组策略仍按 720 秒预算运行。评测器在第 395 秒只读导出当时的两份文件，随后停止运行，并在容器外重新评分。九组均通过传输自检。实际读完的时间为 395.137–395.216 秒，评测器核对目录与文件的 inode / ctime，九次取样均满足截止点的一致性检查。

| 策略 | 395 秒时的 A / B / C 成本（美分） | 395 秒达到最优 | 另一次完整预算达到最优 |
|---|---|---:|---:|
| 原短提示工具循环 | 未交付 / 未交付 / 未交付 | 0/3 | 2/3 |
| 首轮原生 Python 工具调用 | 92 / 67 / 35 | 3/3 | 3/3 |
| 首轮直接生成 Python | 92 / 67 / 35 | 3/3 | 3/3 |

第 395 秒的三次原流程都尚无输出目录，三次首轮程序都有非零退出码。汇总两轮、每种策略六次首轮请求，文本方式平均产出 1,112 个 token，原生工具方式为 1,297 个。两种策略在这些任务的分数相同。基于首次生成开销，云端 Gemma CPU 开发流程对符合条件的任务自动使用文本 Python，固定零温度与种子 17；GPT-6.1 Sol 和参赛配置 GLM-5.2 保持原有策略。两个时间点来自不同运行器，不代表三道题之外的得分表现。[395 秒快照与独立评分](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45207676461)

### Excel 输入取证

旧工具读取工作簿只返回二进制长度。新工具在题目容器内使用 `openpyxl` 只读预览指定工作表和最多 96 个单元格。保留单元格坐标、公式和上次保存的缓存值。工作表声明的使用范围只作为定位提示。原创工作簿中，E7 为 12，E8 的公式为 `=E7*2`，而上次保存的值为 20。测试同时覆盖缓存为零、缺失缓存、隐藏工作表和非默认区域，检查读取前后文件哈希一致。题目镜像缺少 `openpyxl` 时，工具会说明依赖缺失。可用安装了 `openpyxl` 的 Python 运行 `python devtools/workbook_regression.py`。[Encoding Spreadsheets for Large Language Models](https://aclanthology.org/2024.emnlp-main.1154/) · [openpyxl 读取语义](https://openpyxl.readthedocs.io/en/stable/tutorial.html)

两个独立的 GPT-6.1 Sol 会话各接收一次对同一本工作簿的真实 `read_file` 返回，回答相同四问。旧工具只返回 5,497 字节的二进制标记，模型四项均回答未知。新工具让模型答对可见工作表、隐藏工作表、E8 的公式与缓存、独立复算及差异这四项。每组各一轮，模型没有其他工具可用；该试验只测一次读取能提供多少证据。缓存为 `null` 表示读取器没有给出值，空字符串缓存和缺失缓存都可能产生这个结果。

## 判读边界

官方公开开发榜按 29 道题汇总，每个模型和 harness 组合运行三次。Gemma 4 26B 在所列组合中的分数为 0.007 至 0.053，GLM 5.2 配 Codex 为 0.260。公开榜的模型服务、推理设置和预算与本项目在四核 CPU 上使用的量化模型不同。正式对照要固定模型服务、模型版本、每题时间和评测器，再比较同一批题的逐题分数和产物。[开发榜](https://ple-bench.com/leaderboard?set=dev) · [官方产物规范](https://github.com/google-research/ple/blob/8320f0402fdca9f42476607f72bcfd5271cd50c9/docs/artifacts.md)

正式开发题需要评测进程获得受限数据集的读取权。账户批准访问与 GitHub 运行器换到只读凭据是两个单独的步骤。Hugging Face 的账户 CI/CD identity 可给特定仓库、分支和 workflow 签发短时 `gated-repos` 凭据。CPU 路径只需要读题权限。本次运行器返回 `invalid_grant`，后续设备登录等待超时。修复后的选择器还能区分凭据缺失、拒绝和临时不可用，重新运行后记录为当前没有可用的读题凭据，未产生正式分数。[更新后复验](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45187485602)[正式题记录](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45185198336) · [Hugging Face 身份配置说明](https://huggingface.co/docs/hub/trusted-publishers)

Excel 改动提交后再次运行，官方 kit 的配置校验和独立工作簿回归均通过。工作流身份交换仍返回 `invalid_grant`，凭据选择器也未找到可读取受限题集的凭据，流程止于下载，正式模型和评分步骤均未启动。[云端复跑](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45204574378/job/137796706042)
