# 土木交付自检表

## 通用

- [hard] 交付物在题面指定路径，文件名逐字符一致
- [hard] 文件可解析（docx / xlsx / zip）
- [hard] 全文日期自洽，且锚在题面给的基准日
- [hard] 判定二值（ACCEPTED / REJECTED、comply / not comply），不写"基本满足"
- [soft] 有约束台账或 equivalent 判据表

## 备忘录（memo）

- [hard] 单个 docx，文件名与题面一致
- [hard] 抬头块含 TO / FROM / DATE / RE
- [hard] 第一节是 `Purpose and Bottom Line` 或 `Bottom line`，结论在此
- [hard] `Dispositions` 用表，列 `No. / Question / Disposition`
- [soft] 参数对照表四列：`Parameter / 原批准值 / 本次值 / 初算`
- [soft] 修订清单（consequential edits）单列一节
- [hard] 若题面要求附件，附件在正文后且被正文引用

## 验收记录

- [hard] 两件都要交：`.xlsx` 记录 + `.docx` 判定
- [hard] xlsx 工作表含 `Cover / Daily Placement Log / Notes / Signature`
- [hard] docx 用业主模板（若目录里有 TEMPLATE 文件）
- [hard] 五个一级章节齐全：PURPOSE / DOCUMENTS REVIEWED / BASIS OF REVIEW / FINDINGS / CONCLUSION
- [hard] FINDINGS 表逐项给 Result，不是一行总结
- [hard] BASIS 里有判据推导（如最大干密度与最优含水率的来源）
- [soft] 判定后列明补救要求与责任方

## 输送方案

- [hard] `conveyance_study.xlsx` 含 `Items / Alternatives / Takeoff / LaborRates / Markups / Register / Findings`
- [hard] `conveyance_study_report.md` 含 `Summary of recommendations` 与 `Estimating basis`
- [hard] 每个 item 给出 route 长度与总价
- [soft] 单价来源可追（LaborRates / EquipmentRates / Markups 三张表齐全）
- [hard] 推荐方案与 Alternatives 表一致，不能正文推荐 A 而表里选 B

## 收尾

- [hard] `done.final_message` 点名每个文件路径
- [soft] 三段式 + 对照表
