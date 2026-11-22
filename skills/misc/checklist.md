# 杂项交付自检表

## 通用

- [hard] 交付物在题面指定路径
- [hard] 文件可解析（docx ≥ 5 段、ifc 能被 oracle 读）
- [hard] 第一个一级标题是 Disposition / Bottom line / Summary，不是背景
- [hard] 判定二值，且明确"能否关闭"
- [hard] 文号与日期与文件系统里的原文件一致
- [soft] 有"应当 vs 实际"双列表

## 技术说明（CFD / 消防）

- [hard] 有 `Item / Disposition` 表
- [hard] 有 `Record / File / Originator` 表
- [hard] 每个数值成对：给定 / 实测 / 应达
- [hard] 表格编号与正文引用一致，不自行补齐缺失编号
- [soft] 章节 3.1~3.4 的四段结构保留
- [soft] 结论段写明"需要谁做什么"

## 验证 memo（试验对照）

- [hard] To 行有姓名 + 职务
- [hard] 表 1 是"认证几何 / 图纸 / 运行几何"三列对照
- [hard] 表 2 有判据、限值与穿越时间
- [hard] 表 3 的 Rollup 顺序与题目指定程序节序一致
- [hard] 误差列写作 `E = S − D`，并附 `u_val`
- [soft] 第 5 节给出修正后的实验值

## 造价核对

- [hard] Summary 里给出修正后总额与差额
- [hard] 逐行 Change 列（不是只给总差）
- [hard] 单价与数量变动分开列
- [soft] 有 "Lines confirmed or carried without change" 一节
- [soft] 有 "What could still move Section 2" 风险节

## IFC 模型

- [hard] 交付 `submission/model.ifc`
- [hard] 用 `oracle_client.py` 自检通过（题面给了就必须跑）
- [hard] 覆盖题面要求的分期
- [hard] 不落在禁用区（湿地/缓冲/地役权范围）
- [soft] `done.final_message` 说明布局决策与理由

## 收尾

- [hard] `done.final_message` 点名文件路径
- [soft] 三段式：What's in it / What I decided / 风险
