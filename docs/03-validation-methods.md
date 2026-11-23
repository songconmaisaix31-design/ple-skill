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

## 判读边界

官方公开开发榜按 29 道题汇总，每个模型和 harness 组合运行三次。Gemma 4 26B 在所列组合中的分数为 0.007 至 0.053，GLM 5.2 配 Codex 为 0.260。公开榜的模型服务、推理设置和预算与本项目在四核 CPU 上使用的量化模型不同。正式对照要固定模型服务、模型版本、每题时间和评测器，再比较同一批题的逐题分数和产物。[开发榜](https://ple-bench.com/leaderboard?set=dev) · [官方产物规范](https://github.com/google-research/ple/blob/8320f0402fdca9f42476607f72bcfd5271cd50c9/docs/artifacts.md)

正式开发题需要评测进程获得受限数据集的读取权。账户批准访问与 GitHub 运行器换到只读凭据是两个单独的步骤。Hugging Face 的账户 CI/CD identity 可给特定仓库、分支和 workflow 签发短时 `gated-repos` 凭据。CPU 路径只需要读题权限。本次运行器返回 `invalid_grant`，后续设备登录等待超时。修复后的选择器还能区分凭据缺失、拒绝和临时不可用，重新运行后记录为当前没有可用的读题凭据，未产生正式分数。[更新后复验](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45187485602)[正式题记录](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45185198336) · [Hugging Face 身份配置说明](https://huggingface.co/docs/hub/trusted-publishers)
