# 01 — spec-first：在模型开口之前，把验收标准定死

这个 harness 的第一行代码不是决策循环，是 `skillkit/specgen.py`。
原因很功利：**如果模型不知道"交到哪"，它做的所有工程判断都只是在给一个错路径增加说服力。**

## 题面有两种，长得完全不一样

我把 29 条 instruction 逐条读下来，分成两类：

**A 类（长，>5000 字符）** —— 自带交付清单，结构规整：

```
## Deliverables
### 1. `design_basis.md`
...
### 2. `wire_schedule.csv`
Columns, exactly these names:
```csv
circuit,description,from,to,install_class,length_ft,...
```
```

这种可以精确抽。`lv-cable-sizing` 的 `wire_schedule.csv` 我抽到 27 列，和 baseline 实际产出
的 28 列只差一列（`drop_v` 在表尾，题面里写作计算列）。够用。

**B 类（短，<2000 字符）** —— 真正的交付要求写在 `task.md` 里，instruction 只有一句自然语言：

> Save it as /filesystem/Halbray_Backfeed_Reply.docx.

或者更绕的：

> Put it in a Word note saved as /filesystem/CFDME-2025-041_resolution_note_revA.docx please.

甚至完全不写路径，只有：

> Use the attached memorandum form and keep its sections. Write it from Rahul Nimkar,
> Geotechnical Reviewer, to Adrian Vance, Project Engineer...

B 类是主要失分来源。**因为路径不是"数据"，是"句子"。**

## 两个正则坑，都是我自己写出来的

第一版只处理 A 类 + 反引号里的路径，29 条里命中 14 条。全部 B 类失败。

**坑 1：我允许路径里有空格。**

```python
r"...(?:as|to|at|in)\s+([/A-Za-z0-9_][A-Za-z0-9_./\- ]{2,140}\.(?:zip|docx|...))"
#                                                        ↑ 这里多了个空格
```

于是 `"a Word note saved as /filesystem/x.docx"` 整串被当成路径。我在输出里看到
`deliverable: a Word note saved as /filesystem/CFDME-2025-041_resolution_note_revA.docx`
——它甚至"看起来"像对的，一样以 `.docx` 结尾。这种 bug 最危险，因为它不报错。

**坑 2：收紧之后，路径第一个字符不能是 `/`。**

```python
r"([A-Za-z0-9_][A-Za-z0-9_./\-]{2,140}\.(?:docx|zip|...))"
#   ↑ 首字符类里没有 /
```

而几乎所有绝对路径都以 `/filesystem/` 开头。这一改，命中数从 14 掉到 0。
那个瞬间我以为自己改坏了整个模块。

最后是加回 `/`、同时禁止空格，命中才从 14 跳到 23，再补上目录型交付到 25。

**教训**：路径解析的失败是静默的。所以 `specgen` 输出的 `confidence` 字段必须被下游读——
`confidence=low` 时，system prompt 里会明确写一句"路径未知，先自己确立再动手"，而不是假装知道。

## 目录型交付：第三种

有些题不点名文件，只说：

```
## Where to put your answer
Save the files that make up your answer under `output/` in this workspace,
... Files you copy into `output/` are read as part of your answer.
```

这类我加了 `mode="dir"`，`deliverable="output/"`，守卫改成"目录非空 + 内部 docx/xlsx 可解析"。
`fire-test-validation-memo` 和 `landscape-sheet-revision` 就是这么解出来的。

## 剩下的 4 道

`data-hall-mep-routing-offset`、`footing-settlement-verification`、`solar-supplemental-review`、
`solar-witness-test-package` —— 题面里完全没有路径，只有内容要求。

我的处理不是猜一个文件名，而是**标 `confidence=low` 交给运行时**：

- system prompt 里明说"交付路径未在题面中出现，先 `cat task.md`、找 house 模板、按命名惯例确立，
  并在 final_message 里说明你的选择"
- harness 在第一次探索时先 `cat task.md`，如果 `task.md` 里有交付要求，**回灌 specgen 重解析**
  并覆盖合同

这条路我实现了，但它依赖 `task.md` 在 workdir 根目录。这是已知缺口，不是已解决问题。
写在这里而不是藏起来，因为 `criteria.py` 的 G-06 就写着 25/29，剩下的 4 条在哪、为什么，
得有人能一眼查到。

## 一句话总结

spec-first 的收益不是"少走几步"，是**把一类系统性失分从概率问题变成确定性问题**：
路径错了，守卫会拦；路径没写，系统知道自己在猜。
