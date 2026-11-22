# 02 — 守卫：为什么只做结构性检查就够了

`skills/_shared/validate.py` 只有 150 行左右，退出码 0/1/2。
它只查**这类问题**：文件在不在、能不能打开、zip 里该有的成员有没有、CSV 的列头是不是题面那 27 个、
docx 的段落数是不是少于 5。**它从不判断工程内容对不对。**

这是刻意的。

## 为什么不判内容

判断"这版隔板设计合不合理"需要领域判断，而领域判断的假阴性率很高——
一个正确的答案用了非惯常的表达，就会被判错。守卫一旦误报，模型就会去改一个本来正确的东西，
这在 6 小时里是最贵的浪费。

内容对不对，grader 和 rubric judge 会判。守卫的职责只有一件：
**拦住那些"必然零分"的形态错误。**

## 一个真 bug：命名空间双括号

xlsx 检查最初这么写：

```python
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
...
for s in wb.iter():
    if s.tag == S + "}sheet":        # S 里已经有 "}" 了
```

`S` 已经以 `}` 结尾，再加一个 `}`，实际匹配的是 `...main}}sheet`。
后果：**所有嵌套 xlsx 都被报"无 sheet"**，包括那些完全正常的。

这个 bug 很阴，因为它是"只误报、不误放"——文件真的坏和文件是好的，都被判坏。
外壳看不出来，得打开一个真实产出对一遍才发现。

改成按 localname 匹配后修好：

```python
if s.tag.split("}")[-1] == "sheet":
```

修完之后我在真实产出上批量验证：11 份 zip PASS、`lv-cable-sizing`（5 项成员 / 27 列 / 2 个嵌套 xlsx）
PASS、`mv-conveyance-study`（11 sheets）PASS、`life-cycle cost`（3 套算稿 × 5 sheets）PASS。

## 第二个 bug 更贵：把输入当成了交付件

合同最初把题面里出现的所有文件名都当成 zip 的必需成员。结果 `task.md`、`*_TEMPLATE.xlsx`
这些**输入**也被要求出现在交付 zip 里。

批量回归时 27 道题只过了 10 道。看失败原因，一半是这一条：

```
FAIL  zip: 缺必需文件 task.md
FAIL  zip: 缺必需文件 conveyance_study_TEMPLATE.xlsx
```

修法是硬/软分离：

- **hard**：`.md` / `.csv`，且不是 `task.md`、`README`、含 `template` 的
- **soft**：`.xlsx` / `.dxf` / `.json` / `.docx` —— 缺了只 WARN

理由：模板是"被填的"，不是"被交的"；图纸和算稿经常是输入。这道区分让回归从 10 过变成 16 过，
另外 2 道从 FAIL 降成 WARN。

**这一条比任何 prompt 技巧都值钱**：错判 hard 会让 agent 永远过不了守卫。

## 熔断：守卫也可能错

合同是机器从题面抽的，就有抽偏的可能。如果一直拒，agent 会在一个错路径上把 6 小时烧完。

所以三次连续拒绝之后，逻辑切换：

```python
if self._guard_fails >= 3:
    self.final = ("CONTRACT DISCREPANCY - the parser-inferred path could not be "
                  "satisfied:\n" + rep[-900:] + "\n\n" + self.final)
```

带着 discrepancy 说明交付，而不是继续循环。

这个取舍不好看：**它等于承认"我可能拦错了，宁可交一个名字不对的东西"**。
但两种情况对比——交一个名字错但内容完整的包（可能拿部分分）vs 什么都不交（拿 0）——
前者严格更好。所以熔断不是妥协，是赔率计算。

## 闭环验证

没有 Docker、没有 key 的情况下，我怎么证明这条链是活的？

`dryrun.py` 用 stub 模型演一场戏，故意走坏路径：

1. `exec` 探索
2. 在合同路径上写一个**空文件**
3. `finish` → **守卫 FAIL，拒绝**
4. `exec` 生成合法 docx
5. `finish` → **守卫 PASS，放行**

输出就是这两行，靠它判断整条链没断：

```
guard at finish: FAIL
guard at finish: PASS
```

`criteria.py` 的 G-09 检查的就是这两行 + 退出码 + 文件存在。

## 一句话总结

守卫的价值不在于它多聪明，在于它**不可被模型绕过**：
模型说"我做完了"不算，得守卫说"这能打开、名字对、列头齐"。
