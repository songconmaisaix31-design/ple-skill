---
name: ple-structural
domain: structural
scope: 结构 / 岩土类隔板剪力、楼屋面设计、临时工程、审图与验算交付包
---

# 结构 / 岩土

## 子型判定

| 子型 | 识别信号 | 交付 |
|---|---|---|
| **隔板剪力** | diaphragm shear / shear wall loads | `.zip`（表 + 算稿 + 台账 + 依据） |
| **楼面/屋面设计** | roof deck / slab design + 雪/风/震 | `.zip`（分区表 + 设计算稿 + BOM + dxf） |
| **工序/临时工程** | phased / occupied floor / method package | `.zip`（工序表 + 稳定性校核 + 占用报告 + method_note） |
| **审图** | EOR review / review comments / markup | `.zip`（处置台账 + 图纸索引 + 修订记录） |
| **验算备忘录** | verification memo / review of submittal | 单个 `.docx` |
| **基础方案** | foundation strategy | `.zip` |

## 工作法

1. **先锁规范版本与失效组合**。`design_basis.md` 第一节永远写"哪些文件管、冲突怎么解决"。常见 ASCE 7 / IBC / 项目 criteria 三层。
2. **参数先落 JSON/表，再算**。把假设、单位、来源固化成 `DesignBasis` 之类的结构化表，再进入计算，便于复核。
3. **分区（zoning）要早做**。屋面/楼板题的分数大头在"分成几个区、每区取什么控制工况"。
4. **每个结论都能追到一个 `stage_id` / `zone`**。校核表每行都要有 `verdict`，不要写"总体安全"这种不可核验的话。

## 必需件与列头（通用格式惯例）

### 隔板剪力（zip）
`diaphragm_shear.csv` + `calc_book.xlsx` + `constraint_register.csv` + `design_basis.md`

### 楼面/屋面（zip）
`deck_design.xlsx` 常见工作表组：`Zones` `DesignBasis` `Drifts` `CalcSummary` `Diaphragm` `BOM`
`design_basis.md` 章节：
```
1. Governing documents and how conflicts were resolved
2. Snow basis
3. Wind uplift basis
4. Seismic basis
5. Diaphragm analysis and classification
6. Zoning decisions
7. Coordination items
```

### 工序 / 临时工程（zip）
| 文件 | 列头（照题面要求调整） |
|---|---|
| `construction_sequence.csv` | `activity_id,zone,level,activity_type,predecessors,duration_days,start_day,finish_day,crew,crane_hours,workspace_volume_cf,gang_id,daily_crane_draw,volume_basis` |
| `stability_check.csv` | `stage_id,zone,level,lateral_system,demand_lb,capacity_lb,verdict,wind_case,notional_case,vertical_load_supported,governing_case` |
| `occupancy_report.csv` | `zone_lift,zone,level,occupied_from_day,occupied_to_day,shored_from_day,shored_to_day,crane_hours_total,laydown_units` |
| `constraint_register.csv` | `requirement,document,clause,value,unit,items_bound,description,applied_as` |

`method_note.md` 章节：`1. Which document governs where the issued set disagrees / 2. Striking and reshoring method adopted / 3. Programme / 4. The constraint that governs each zone / 5. Temporary works design / 6. Margins applied / 7. Attribution`

`temporary_works.json`：设计人资质、验算假设、审批链。

### 审图（zip）
| 文件 | 列头（大写，照题面要求调整） |
|---|---|
| `disposition_register.csv` | `PACKAGE,COMMENT_ID,AUTHOR,SIGNIFICANCE,VALIDITY,VOID_REASON,RESPONSE,RESOLUTION,PRIMARY_SHEET,PRIMARY_VIEW,CHANGE_KIND,SHEETS_CHANGED,SHEETS_IMPACTED,CLOSURE` |
| `issue_plan.csv` | `PACKAGE,BUNDLE_ID,BUNDLE_FILE,SHEET_NUMBER,DISCIPLINE_DESIGNATOR,PLOT_PDF_MB,BUNDLE_SEQ` |
| `revision_log.csv` | `PACKAGE,SHEET_NUMBER,MARK,DESCRIPTION,DATE,ROW_POSITION,OVERFLOW_OPTION` |
| `sheet_index.csv` | `PACKAGE,INDEX_ORDER,SHEET_NUMBER,SHEET_NAME,CURRENT_REVISION,ISSUE_ACTION,IN_THIS_ISSUE` |

`design_basis.md` 用 `A. / B. / C.` 大写字母分节，不是数字。
`continuation_sheet.md` 是给合同官的变更说明，按 package 分段。

**审图类任务的核心判断是"哪条意见可以合法地直接改"**——要区分 mark-up 的作者权限（设计方能改，施工方不能），这个判断写进 design_basis 的 `B. Which markups can direct a change`。

### 验算备忘录（docx）
固定骨架（工作区里出现 `*_TEMPLATE*.docx` 就必须套模板）：
```
[公司抬头]
VERIFICATION MEMORANDUM
From: / Date:
1.  PURPOSE
2.  DOCUMENTS REVIEWED          ← 表：Ref. / Document / Revision / Date
3.  BASIS OF REVIEW
 3.1 Governing requirements
 3.2 Review method               ← 公式原文写在这里
4.  FINDINGS                     ← 表：Case / 输入 / 结果
5.  CONCLUSION AND RECOMMENDATION   ← 明确 VERIFIED / NOT VERIFIED
[署名块]
```

## 常见死法

- 只给最终数值，不给中间量（σ'0、Δσ、e0 都要在表里）
- 验算结论写"基本满足"——必须是二值判定 + 遗留条件
- 审图题漏 `VOID_REASON`：无效意见必须写明为什么无效
- 工序题 `predecessors` 写成自然语言而不是 activity_id
- 借用模板时忘了换项目名和日期
