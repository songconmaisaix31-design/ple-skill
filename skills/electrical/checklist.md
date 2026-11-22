# 电气交付自检表

提交前逐项过。`[hard]` 违反 = 0 分，`[soft]` 违反 = 扣分。

## 通用

- [hard] 交付物写在题面指定的精确路径（含大小写、连字符、`output/` 前缀）
- [hard] 文件能被标准工具打开（docx / xlsx / zip 均可解析）
- [hard] 非空：docx ≥ 5 段，xlsx ≥ 1 sheet，zip ≥ 1 项
- [hard] zip 内部至少有 `design_basis.md` 或 `basis.md`
- [hard] 有约束台账（`constraint_register` 或 `register`）
- [soft] 台账列含 `requirement, document, clause, value, unit`
- [soft] `clause` 是真实条款号或显式 `unknown`，不是空
- [hard] 所有题面点名的表都在
- [soft] csv 列头与题面字面一致（不自行改名、不改顺序）

## 函件型

- [hard] 单个 docx，文件名与题面一致
- [hard] 开头有收件人块 + 日期 + Re 行
- [hard] 结论出现在正文第一部分
- [soft] 逐条不符合项用表格，列头 `# / What the schedules show / NEC requirement / What has to be done`
- [soft] 行动表列头 `Step / Action / By whom / When`
- [hard] 基准日期与题面一致，全文不出现"今天"

## 清单 / BOM 型

- [hard] `bom.csv` 列头 `line_item,description,for_type_mark,condition,quantity,unit,unit_price,extended_price`
- [hard] `takeoff.csv` 与 `bom.csv` 数量能对上（takeoff 合计 = bom 同 type_mark 合计）
- [soft] `locations.csv` 的 `grid_bay` 与图纸网格线一致
- [soft] `basis.md` 含"计数约定"和"未解决符号"两节

## 规范型

- [hard] spec 文件按 CSI 编号命名（`26 05 73.docx` 形式）
- [hard] 每个 spec 有 PART 1 / 2 / 3
- [soft] `design_basis.xlsx` 含 `Register` 与 `Findings` 两个工作表
- [soft] 馈线表、短路表、照度表各自的列头齐全

## 计算表型

- [hard] `wire_schedule.csv` 列头含 `circuit,description,from,to,size,design_current_a,corrected_ampacity_a,vd_pct`
- [hard] `corrected_ampacity_a >= design_current_a` 对每一行成立
- [hard] `vd_pct` 在题面给定的预算内（逐行 + 累计都要满足）
- [soft] 有算稿（`calc_book.xlsx`）且 sheet 数与计算步骤对应
- [soft] 图纸 `.dxf` 有合理图层名，不是单一 layer
- [hard] `design_basis.md` 第一节写了冲突优先级

## 收尾

- [hard] `done.final_message` 非空，且点名每个文件的路径
- [soft] 三段式：What's in it / What I decided / Choices that could cost credit
