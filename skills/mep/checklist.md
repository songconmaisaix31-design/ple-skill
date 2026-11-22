# MEP 交付自检表

## 通用

- [hard] 交付物在题面指定路径，文件名逐字符一致
- [hard] 文件可解析（zip 能开、docx ≥ 5 段、xlsx ≥ 1 sheet、.py 能 import）
- [hard] 有约束台账（`constraint_register.csv`）与依据文件
- [hard] 所有计算按 `circuit_id` / 设备单元分桶，没有跨桶合并
- [soft] 台账列 `id,document,clause,requirement,value,items_bound`

## MOP 程序包

- [hard] `MOP.md` 存在，且第 2 节写明"以哪一版 P&ID 为准"
- [hard] 五张 csv 齐全：flush_plan / chemistry_plan / acceptance_matrix / schedule / constraint_register
- [hard] `flush_plan.csv` 每行有 `velocity_fps, reynolds, required_head_ft, skid_head_avail_ft`
- [hard] `required_head_ft <= skid_head_avail_ft`（不满足就必须换 skid 或降流，不能留矛盾行）
- [hard] `chemistry_plan.csv` 的 `basis_volume_gal` 与 `flush_plan` 的体积一致
- [hard] `acceptance_matrix.csv` 每行有 `basis_doc` 和 `basis_clause`
- [soft] `schedule.csv` 的 `predecessor_ids` 用 activity_id
- [soft] `resources.json` 的 skid_assignment 三级嵌套完整

## 布线程序

- [hard] 交付物是 `output/solution.py`
- [hard] 能被 import / 直接运行，无语法错、无缺依赖
- [hard] 输出结构可被解析（JSON 或 csv，字段名与题面一致）
- [hard] 不硬编码题面坐标（违反反作弊）
- [soft] 有冲突检测与避让排序逻辑，不是纯随机落点
- [soft] 覆盖题面点名的所有系统（M / E / F）

## 寿命周期成本

- [hard] 每套 plant 一份算稿（题面要求几套就几份）
- [hard] 算稿工作表组含 `DesignPoint / OffDesign / WaterBalance / Energy / LifeCycleCost`
- [soft] 每套 plant 一份 dxf 排布
- [hard] `design_basis.md` 含 `Documented conflicts` 与 `Judgement calls and margins`
- [hard] 汇总表给出每 plant 的 governing constraint

## 收尾

- [hard] `done.final_message` 点名每个文件路径
- [soft] 三段式 + 关键对照表
