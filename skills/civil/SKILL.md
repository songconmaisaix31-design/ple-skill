---
name: ple-civil
domain: civil
scope: 土木 / 水利 / 景观 / 场地类工程文档与计算交付包
---

# 土木 / 水利 / 景观 / 场地

## 子型判定

| 子型 | 识别信号 | 交付 |
|---|---|---|
| **备忘录（memo）** | TO: 某人 / 日期 / 图号修订 / reach a date | 单个 `.docx`（常 10+ 页，带附件） |
| **验收记录** | acceptance record / compaction / test results | `.xlsx` + `.docx`（两份都要） |
| **输送方案** | conveyance study / route / cost per item | `.zip`（xlsx 多表 + report.md） |

## 工作法

1. **memo 型先给 Bottom Line**。这类 memo 的第一节通常是 `Purpose and Bottom Line` 或 `Bottom line`——结论在最前，后面才是推导。不要写成"分析-分析-结论"。
2. **套业主模板**。工作区里出现 `*_TEMPLATE*.docx` 这类文件时，就说明必须套：抬头、署名块、日期位置都不能重排。
3. **判定必须二值且逐项**。验收类：`ACCEPTED / REJECTED`，且每个测试项单独给 Result。禁止"总体合格，个别需关注"。
4. **日期是硬约束**。这类 memo 常围绕一个承诺日期展开。全文所有日期必须自洽，且与题面或工作区文件给出的"基准日"一致。
5. **中间量必须留在表里**。干密度、含水率、与最大干密度的比值、限值，四列并列，缺一行就无法复核。

## 必需件与列头（通用格式惯例）

### memo（docx）
同类 memo 可共用一个骨架：
```
[公司抬头]
MEMORANDUM
TO: / FROM: / DATE: / RE:
1. Purpose and Bottom Line
2. Dispositions                ← 表：No. / Question / Disposition
3. The <设施> as Drawn
4. Amendment to <已批准的上一版文件>
5. The Revised Sheet <图号>
 5.1 Design basis
 5.2 <构件> detail — values     ← 表：Parameter / 原值 / 新值 / 初算
 5.3 <构件> detail — section and erosion protection
 5.4 Basin notes
 5.5 Consequential edits in the same revision
Attachments A / B / ...
```

### 验收记录（xlsx + docx）
xlsx 工作表组常见形态：
```
Cover / Daily Placement Log / Notes / Signature
```
docx 用业主模板，五个一级章节：
```
1. PURPOSE
2. DOCUMENTS REVIEWED      ← 表：# / Document / Date / Cited as
3. BASIS OF REVIEW         ← 含判据推导与输入取值
4. FINDINGS                ← 表：Test / Location / 实测 / % / 限值 / 结果
5. CONCLUSION AND RECOMMENDATION   ← Determination: REJECTED / ACCEPTED
```

### 输送方案（zip）
多表工作簿常见工作表组（照题面要求调整）：
```
Items / Segments / Structures / Pulls / Alternatives / Takeoff /
LaborRates / EquipmentRates / Markups / Register / Findings
```
报告章节：
```
1. Summary of recommendations
2. Estimating basis
   Labor rates used / Crew rates used / Equipment rates used /
   Material unit rates used / Labor units used
3. Item studies
```

收尾用一张对照表：`Item / Recommended / Cable / Route (ft) / Total project cost`。

## 常见死法

- memo 写成论文式（背景→分析→建议），结论不在最前 → 判"不专业"
- 验收题只给结论不给逐项 Result
- 用了业主模板但改了署名块/页眉 → 格式分直接没
- 输送方案只给总价，不给单价来源（LaborRates/Markups 两张表是核价依据）
- memo 里的日期与附件日期互相矛盾；日期链常被重点核查
