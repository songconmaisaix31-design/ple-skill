---
name: ple-deliverable-core
description: PLE 工程交付物的通用骨架。任何 domain 的交付包都先套这一层，再接领域 skill。
---

# 通用交付骨架（从 29 份真实 artifacts 反推）

## 一、五件套

29 份产出里，凡是 zip 型交付（12 题），几乎都由这五类文件组成。缺任何一类，grader 都会扣分。

| 件 | 典型文件名 | 作用 | 是否几乎必有 |
|---|---|---|---|
| **依据** | `design_basis.md` / `basis.md` | 说明规范版本、冲突时的优先级、参数来源 | 是 |
| **约束台账** | `constraint_register.csv` / `.xlsx` | 每条约束：来源文件 + 条款号 + 取值 + 单位 + 怎么满足的 | 是 |
| **主交付表** | `*.csv` / `*.xlsx` / `*.dxf` | 真正的工程成果（线缆表、BOM、剪力表） | 是 |
| **结构化参数** | `*.json` | 给机器读的参数与假设 | 常见 |
| **收尾摘要** | `done.final_message` | 给 rubric judge 读的说明 | 是（评分项） |

## 二、约束台账的通用列

跨 domain 反复出现，几乎可以直接当模板：

```
requirement, document, clause, value, unit, items_bound, description, applied_as
```

变体：`family, document, clause, value, how_satisfied`（device takeoff 用）；
`PACKAGE, COMMENT_ID, AUTHOR, SIGNIFICANCE, VALIDITY, RESPONSE, RESOLUTION, CLOSURE`（EOR 审图用）。

**规则**：`clause` 必须写真实的条款号（NEC 300.6、ASCE 7-22 §12.10.1、IBC 2021 1607.1）。写不出条款号就写 `unknown`，不要编。

## 三、收尾摘要的三段式

从 29 份 `final_message.md` 归纳出的高频结构：

```
**What's in it**        # 交了哪几个文件，各是什么
**What I decided**      # 关键决策 + 依据条款
**Choices that could cost credit**   # 自己知道有风险的地方，主动挑明
```

第三段是差异点——baseline 的摘要里反复出现 "Choices that could cost credit"，说明它在主动暴露不确定性。judge 读这个。

## 四、时间策略（硬规则）

- `agent_timeout_sec = 21600`（6 小时），单条 exec 上限 600 秒
- baseline 29 题平均 **84 步/题**
- 题面明确要求："在前 ~100 步内写出第一版完整交付物，然后原地迭代"
- **推论：第 15~25 步就必须有一个能打开的最小完整包**，哪怕内容空

## 五、硬约束 vs 软约束

| 级别 | 内容 | 违反后果 |
|---|---|---|
| `[hard]` | 交付路径、文件名、zip 结构、文件能打开、csv 有列头 | 直接 0 分 |
| `[soft]` | 章节顺序、单位风格、列顺序、表格样式 | 扣分但可救 |

`validate.py` 只对 `[hard]` fail，`[soft]` 只 warn。**这条设计是为了避免 skill 把模型锁死。**

## 六、禁止

- 不写具体题目的答案数值（反作弊条款：不得硬编码、不得按题指纹写逻辑）
- 只写"这类文件长什么样"，不写"这道题选几号线"
