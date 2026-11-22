# 结构交付自检表

## 通用

- [hard] 交付物在题面指定路径，文件名逐字符一致
- [hard] 文件可解析（zip 能开、docx ≥ 5 段、xlsx ≥ 1 sheet）
- [hard] zip 内含 `design_basis.md`（或 `method_note.md`）
- [hard] 有约束台账
- [soft] 台账列 `requirement,document,clause,value,unit,items_bound,description,applied_as`
- [hard] 每条结论可追溯到 zone / stage_id / case 编号
- [hard] 二值判定（VERIFIED / NOT VERIFIED、pass / fail），不写"基本满足"

## 隔板剪力

- [hard] 有分区表，每区给出控制工况
- [hard] 有剪力汇总表，单位统一（lb 或 kip，全文一致）
- [soft] 算稿里保留中间量（板宽、跨度、单位剪力）
- [soft] 抗震与抗风分开列，不合并成一列

## 楼面 / 屋面

- [hard] `deck_design.xlsx` 含 `Zones` 与 `BOM`
- [soft] 工作表组 `Zones / DesignBasis / Drifts / CalcSummary / Diaphragm / BOM`
- [hard] `design_basis.md` 含雪、风、震三个 basis 各一节
- [soft] 有 `dxf` 平面，分区边界可见
- [hard] BOM 数量与分区表数量一致

## 工序 / 临时工程

- [hard] `construction_sequence.csv` 的 `predecessors` 用 activity_id
- [hard] `stability_check.csv` 每行有 `verdict`，且 `demand_lb <= capacity_lb` 与 verdict 不矛盾
- [hard] `occupancy_report.csv` 覆盖题面要求的所有 zone
- [soft] `temporary_works.json` 含设计人资质与审批链
- [soft] `method_note.md` 七节齐全

## 审图

- [hard] 四条 csv 齐全（disposition / issue_plan / revision_log / sheet_index）
- [hard] `disposition_register.csv` 列头大写且完整，含 `VOID_REASON` 与 `CLOSURE`
- [hard] 每条 comment 都出现在 disposition 里（题面编号一条不漏）
- [hard] 无效意见写明 void 理由，不是留空
- [soft] `design_basis.md` 用 A/B/C 大写分节
- [soft] `continuation_sheet.md` 按 package 分段

## 验算备忘录

- [hard] 若题面给了业主模板，必须套模板（页眉、署名块、编号都不改）
- [hard] 五个一级章节齐全：PURPOSE / DOCUMENTS REVIEWED / BASIS OF REVIEW / FINDINGS / CONCLUSION
- [hard] 公式原文出现在 BASIS OF REVIEW
- [hard] FINDINGS 有中间量表（不是只给结论）
- [soft] 结论后附遗留条件与责任方

## 收尾

- [hard] `done.final_message` 非空且点名文件路径
- [soft] 三段式：What's in it / What I decided / Choices that could cost credit
