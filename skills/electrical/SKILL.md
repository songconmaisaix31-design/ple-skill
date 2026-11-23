---
name: ple-electrical
domain: electrical
scope: 电气 / 光伏 / 并网类函件、清单、规范与计算表交付包
---

# 电气 / 光伏 / 并网

## 先把子型判对（决定整套交付形态）

| 子型 | 识别信号 | 交付 |
|---|---|---|
| **函件** | 题目里有收件人、来信日期、"reply / response / memo" | 单个 `.docx` |
| **清单** | "takeoff / bill of materials / quantity" | `.zip`（5 件） |
| **规范** | "specifications / Division 26 / submittal" | `.zip`（design_basis + 多个 spec docx） |
| **计算表** | "schedule / sizing / ampacity / voltage drop" | `.zip`（表 + 算稿 + 台账 + 依据 + 图纸） |

## 工作法

1. **先定"记录基准日"**。这类题常给出 "as the records stand at <日期>"。所有判断都锚在这个日期，不要用"现在"。
2. **列约束台账再动手**。规范条款号、项目许可条件、业主 criteria，先进 `constraint_register`，再算。条款号写不出就写 `unknown`。
3. **冲突优先级写进 `design_basis.md` 第一节**。典型顺序：许可条件 > 采纳的规范版本 > 业主 criteria > 图纸。这一节通常就是第一段。
4. **算完立刻写表**，不要先写叙述。
5. **收尾三段式**见 `_shared/SKILL.md`。

## 各子型的必需件与列头（通用格式惯例）

### 函件（docx）
固定骨架：

```
[公司抬头] / 日期 / 收件人块（姓名、职务、单位、地址）
Re: 项目 + 主题
Our answer            ← 结论放最前，一句话能不能
1. 许可条件            ← 引用许可编号 + 原文
2. 记录中的不符合项      ← 表格：# / 图纸显示 / 规范要求 / 要做什么
3. 何时之前必须做什么、由谁做  ← 表格：Step / Action / By whom / When
4. 期间的状态
```

### 清单（zip）
`basis.md` + `bom.csv` + `locations.csv` + `register.csv` + `takeoff.csv`

| 文件 | 列头 |
|---|---|
| `bom.csv` | `line_item,description,for_type_mark,condition,quantity,unit,unit_price,extended_price` |
| `locations.csv` | `sheet,type_mark,grid_bay,condition,count` |
| `takeoff.csv` | `type_mark,description,quantity` |
| `register.csv` | `family,document,clause,value,how_satisfied` |

### 规范（zip）
`design_basis.xlsx`（常见工作表组：`Sections` `Feeders` `ShortCircuit` `Photometric` `BuildingLPD` `StepLoad` `StepLoadCheck` `CumulativeVD` `Register` `Findings`）+ `specs/26 xx xx.docx`
- spec 文件按 **CSI MasterFormat** 编号命名，章节用 PART 1 / 2 / 3
- 每个 spec 里的表格列头是规格的一部分，例如馈线表 `Feeder / From / To / Conductors / Raceway`

### 计算表（zip）
`wire_schedule.csv` + `calc_book.xlsx` + `constraint_register.xlsx` + `design_basis.md` + 图纸 `.dxf`

`wire_schedule.csv` 常见列头：
```
circuit,description,from,to,install_class,length_ft,sets,size,material,
egc_size,raceway_trade_in,duct_ids,design_current_a,corrected_ampacity_a,
vd_load_a,vd_pct
```

`design_basis.md` 章节顺序：
```
Design basis - <表号>, <项目>
1. Codes of record, adopting document, order of precedence
2. Environmental parameters and provenance
3. Load basis and ampacity method
4. Service-entrance sizing decision
5. Voltage-drop budget allocation
6. Duct-bank assignment and thermal consequence
7. Material and standardisation decisions
8. Cost ledger - material and labour
9. Circuit summary
```

## 常见死法

- 只交摘要不交表 → 结构分直接损失
- 列头拼写/顺序与题面不一致（`vd_pct` vs `vd_percent`）→ 结构分全丢
- 用"最新版 NEC"而不是题目指定的年份 → 条款号对不上
- 冲突没写优先级，导致后面所有判断无法追溯
- dxf 用 matplotlib 画图冒充真 CAD 图层 → 打开能开但图层不合规
