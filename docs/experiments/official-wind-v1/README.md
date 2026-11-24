# 正式开发题 wind-diaphragm-shear 的单题交付

### 第五轮：截短最近两条工具结果

第五轮在第四轮省略较早工具结果的基础上，将最近两条工具结果各自限制在 4,096 个 Unicode 字符。脱敏日志记录了 `masked_history` 和 `trimmed_recent`，确认两种处理均已触发。官方生成分仍为 **0/1**。捕获器正常结束，清单记录捕获、导出、跳过均为 0 个文件。空导出遭拒，目标 ZIP 缺失，独立文件重评分缺测。

| 指标 | 第四轮：省略较早结果 | 第五轮：另截短最近两条 | 第五轮减第四轮 |
|---|---:|---:|---:|
| 官方生成分（满分 1） | 0 | 0 | 0 |
| 捕获文件数 | 0 | 0 | 0 |
| 运行秒数 | 2,107 | 5,572 | +3,465 |
| 累计输入 token（含缓存） | 123,554 | 556,464 | +432,910 |
| 其中缓存 token | 86,103 | 499,307 | +413,204 |
| 累计输出 token | 3,706 | 11,881 | +8,175 |

两轮核验了相同的输入树、模型权重、16,384 token 上下文、种子 17、温度 0、套件版本和运行预算，托管机镜像版本均为 `20261116.133.1`。两轮都出现上下文超限与 HTTP 4xx 标记，均未触发运行器超时。归档仅给出整次运行的标记和累计 token，无法定位具体超限请求。每种设置各一次，表中为实测差值，无法据此估计配对样本方差或策略的平均成本。

第五轮命中了预登记的截短条件，仍未交付可重评的 ZIP，按判据停止扩展该策略及其余 28 题。五次正式尝试均来自同一道题，生成评分覆盖 **1/29**，可用交付及独立文件重评覆盖均为 **0/29**。[预登记](../next-round.md) · [第五轮源提交](https://github.com/songconmaisaix31-design/ple-skill/commit/d127279f4c80c27b8bf91311dd652f894bdb45fd) · [第五轮运行及作业](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45370943807/job/138364862309)

第五轮为运行 `45370943807` 的第 1 次尝试。GitHub 工件编号 `14914969961`，原始诊断包 SHA-256 为 `61a8b18ee63ca4f0c23fa9e72fcaa4a3a4200a73f4bb85ae4a0cb90b36e15a39`。[第五轮原始诊断包](recent-tool-excerpt-attempt-1.zip) · [第四轮原始诊断包](masked-history-attempt-1.zip)

### 历史工具结果省略策略

策略已触发。官方生成分 0/1，目标文件捕获 0，独立文件分缺测。运行 2,107 秒，输入 123,554（其中缓存 86,103）、输出 3,706 token。出现上下文超限和 HTTP 4xx；捕获器正常、没有运行器超时。检查器拒绝空导出。基线与本次输入树哈希、模型、采样参数、上下文、套件及时间预算一致；托管机镜像不同。每设置一次，原始分差为 0，不能估计配对样本方差或断言成本收益。按判据停止扩大该策略。

[源提交](https://github.com/songconmaisaix31-design/ple-skill/commit/8ffbfc10445e5c3db4301135aa59ea1360e9c28a) · [运行](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45361598868/job/138332891807) · [原始诊断工件](masked-history-attempt-1.zip)，编号 14907128563，SHA-256 `dde99b8b56d04b4a747ae4b405ba842c66c3c385b70878835ece7c56a0e0b954`。

### 16,384 token 试跑结果

官方生成分 **0/1**。输入目录在两个冻结版本的 SHA-256 相同。捕获器正常结束，捕获和导出文件均为 0。记录中出现上下文超限和 HTTP 4xx，未触发运行器超时。用时 3,801 秒，输入 310,991 token（含 295,236 缓存）、输出 9,654 token。官方导入器拒绝空交付，独立文件重评分缺测。按预登记停止扩展其余 28 题。该配置只跑一次，无法估计配置间的配对差或样本方差。正式覆盖仍为 1/29。

[运行及作业](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45343929236/job/138273957725) · [运行提交](https://github.com/songconmaisaix31-design/ple-skill/commit/4adc832cafe190789d9969861d1f94d35060ac91) · [原始脱敏工件](context-16384-attempt-1.zip)，GitHub 工件 14900957562，SHA-256 `c40b352f354e88046948cb2f29064b01044db87feb4cbc8336bddfbfa2d15bfc`。run.json 可核对原始分，input.json 和 model-runtime.json 可核对输入、模型、种子和实际运行参数。

### 此前 8,192 token 基线


同一题的两次官方检查都记录了 **0/1**。第二次固定模型并记录交付诊断。模型产生了输出，任务结束时官方捕获器正常完成，实际捕获文件数为 0。官方导出审查返回 `empty`，缺少可供独立文件重评的 ZIP。全开发集成绩和比赛排名仍待测。[首轮评分](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45337685121/job/138253542503) · [同模型诊断](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45340782388/job/138263660203)

| 正式单题尝试 | 运行提交 | 官方生成分 | 交付与复评 |
|---|---|---:|---|
| 45337685121，第 1 次 | [663569f](https://github.com/songconmaisaix31-design/ple-skill/commit/663569f514b24e6b86b8638ddb83c4ca8a1e54a0) | 0/1 | 评测器退出码 1，未取得独立文件重评分 |
| 45340782388，第 1 次 | [ce7abfe](https://github.com/songconmaisaix31-design/ple-skill/commit/ce7abfe1ea8968e0cd777793558aaa5b4903152b) | 0/1 | 捕获 0、导出 0、跳过 0 个文件，评测器退出码 1，文件重评分缺测 |

诊断用了 252 秒，官方记录 `measured=true`、`kind=ok`、原始奖励 0。累计输入 12,789 token、输出 81 token，缓存计数 5,815。脱敏日志标记为 `context_limit`、`http_4xx` 和 `export_empty`。现有记录无法定位哪一次请求、哪一段提示或工具返回触及上限，也无法证明扩大上下文一定能产生交付。当前还没有不同上下文配置间的配对观测，配对均值及样本方差均不可估计。[原始诊断 JSON](baseline-diagnostic.json) · [Actions 归档](https://github.com/songconmaisaix31-design/ple-skill/actions/runs/45340782388/artifacts/14896802872)

## 16,384 token 单题试跑预登记

| 项目 | 冻结设置与判据 |
|---|---|
| 问题 | 同一 Gemma 在新导出流程中使用 16,384 token 上下文后，能否生成官方接受且可独立重评的单题交付？历史运行用于描述性参照。 |
| 模型 | 两次历史运行的 CPU 配置为 llama.cpp b12651、8,192 token 上下文。候选的模型服务参数只改为 16,384。保留自托管 Gemma 4 26B A4B IT、UD-IQ2_XXS、温度 0、种子 17、单并发槽、最多四 CPU 线程，以及相同的提交 harness、工具和提示策略。模型文件 SHA-256 为 `52f98e6fc6df62438dff8f57ac049f60b4c36acf93786b6aeeedc129acc02343`。 |
| 数据与评分器 | 单题 `wind-diaphragm-shear`，规则评分。kit 固定为 `8320f0402fdca9f42476607f72bcfd5271cd50c9`。新入口使用任务库 `b3857a3fea39a695e18f845d4a88f29442e96e75`，核对官方目录 SHA-256 `848ac589c41d55ffcd364b6fef9f1dff196c3cc6067a2e630ea0807c818fc5ef`，并重取历史版本 `e0c21fa558c3127785656398e3b3bd7da5e5a5a6` 比较本题目录。缺少历史哈希或哈希不相等时，单列新基线。 |
| 次数与预算 | 生成一次，使用保存的交付在新容器独立重评一次，两阶段均为一次试验、一次尝试。官方题目时限 360 分钟。新流程作业上限 360 分钟，生成调用上限 260 分钟，文件重评调用上限 60 分钟。原诊断作业上限 150 分钟；入口、导出方式及外层预算变更会影响与历史记录的可比性。 |
| 主指标 | 目标 ZIP 已被捕获并列入官方清单；官方审查接受、来源核验通过，且生成和文件重评均完成，分数相同。附记实际上下文、输入哈希、代码版本、run ID 与 attempt、生成分、文件重评分、异常类别和导出哈希。 |
| 继续或停止 | 达到全部交付判据才进入扩展评估。有效 ZIP 得到一致的零分，表示交付与复评流程通过，内容得分仍为零。再次出现空导出、上下文故障或复评分不一致时，停止扩展，保留尝试；技术超时或输入未核验时记缺测。该试跑只决定流程是否可用。 |

单题通关后，若要估计上下文设置的收益，在同一新 runner 上先冻结 8,192 与 16,384 两臂的输入、提交、预算、配对次数及继续门槛，再实施重复试验。原创 T/U 在第 395 秒从文件计分，有独立的配对报告。其分数不进入正式开发题统计。[正式导出及复评协议](../official-export-protocol.md) · [原创 T/U 报告](../actionable-name-error-v1/README.md)
