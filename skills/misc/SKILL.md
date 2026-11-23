---
name: ple-misc
domain: misc
scope: 技术说明 / 造价核对 / CFD / IFC 模型等「判定型」交付物
---

# 技术说明 / 造价核对 / CFD / IFC 模型

这类任务的共同点：**交付的是一份"判定"，不是一份"方案"**。收件人通常是技术总监、业主副总裁或审批方，要的是一句话结论 + 可复核的依据链。

## 子型判定

| 子型 | 识别信号 | 交付 |
|---|---|---|
| **技术说明（Technical Note / Memo）** | disposition / validation / checklist item / bottom line | 单个 `.docx` |
| **造价核对** | estimate check / corrected subtotal / bond | 单个 `.docx`（多张对照表） |
| **IFC 模型** | 3D BIM model / phased campus / `oracle_client.py` | `submission/model.ifc` |

## 工作法（技术说明型）

1. **第一个一级标题就是 Disposition 或 Bottom line**。这类文档不允许"先铺背景"。
2. **建立"应当 vs 实际"的双列表**。常见表格骨架：`Item / Delivered / Status / Shall be`——每一行就是一个不符合项。
3. **数值必须成对出现**：给定值 + 偏差 + 判据。所有取值都从题面或工作区文件读取，不要凭记忆填。
4. **区分"能不能关闭"和"要不要重跑"**。这类题常问某个 checklist item 能否收口：结论通常是"可以收口，但需要 X"或"不能收口，因为 Y 不在文件里"。
5. **日期与文号必须与工作区里的原文件一致**。

## 必需件与结构（通用格式惯例）

### 技术说明（CFD / 消防 / 分辨率）
```
[公司抬头]   TECHNICAL NOTE
Project: <项目号 — 项目名>
1. Disposition                      ← 表：Item / Disposition
2. Record Reviewed                  ← 表：Record / File / Originator
3. The <问题>                       ← 数值：给定 vs 实测 vs 应达
 3.1 What the <对象> should show
 3.2 What attempt N showed
 3.3 How close they are
 3.4 Reading
4. <第二层问题>
 4.1 ...
 4.2 Delivered setup against the standards
```

### 验证 memo（试验对照）
```
MEMORANDUM
To: <姓名, PE — 职务>
1. Bottom line                      ← 是否合格，一句话
2. Sources                          ← 表：Role / Document / Identifier
3. Is the assembly in the run the one certified?   ← 表 1：认证几何 vs 图纸 vs 运行几何
4. Governing criterion and when it is reached      ← 表 2：判据 / 限值 / 试验穿越 / 运行穿越
5. Experimental value and the amended figure
6. Rollup: error, criterion and uncertainty        ← 表 3：S / D / E=S−D / u_val
```
**Rollup 必须按题目指定程序的节序排列**，顺序错了会被认为没读程序。

### 造价核对
```
MEMORANDUM
1. Summary                           ← 修正后总额 + 差额，一句话
2. Basis of the check
3. Quantity and unit-price changes    ← 表 1：No. / Item / Description / Sheet / Rev.0 / Corrected / Change
   Notes to Table 1
5. Corrected Section 2 and bond figure ← 表 3
   Lines confirmed or carried without change
6. What could still move Section 2
[署名块]
```
表格编号与正文引用必须对上；编号以工作区原件为准，不要自行补号。

### IFC 模型
- 交付 `submission/model.ifc`，用题目给的 `oracle_client.py` 自检
- 布局决策要在 `done.final_message` 里说明（讲清楚"为什么放在这个区域"）
- 必须覆盖题面要求的**分期**（phase）与**禁用区**

## 常见死法

- 技术说明写成方案书（"建议进一步…"）→ 判"没做判定"
- 双列表只有"实际"没有"应当"→ 无法核验
- 造价核对把差额算对但没给逐行 Change → 不可复核
- 验证 memo 的 Rollup 顺序与程序节序不一致
- IFC 只交几何不交分期，或压到禁用区上
- 文号/日期与工作区里的原文件不一致
