---
name: ple-mep
domain: mep
covers: cooling-water-flush-plan, data-hall-mep-routing, data-hall-mep-routing-offset, heat-rejection-life-cycle-cost
---

# 机械 / 机电 / 冷却水

## 子型判定

| 子型 | 识别信号 | 交付 |
|---|---|---|
| **MOP 程序包** | flush / cleaning / passivation / turnover | `.zip`（MOP.md + 5 表 + resources.json） |
| **几何布线程序** | "route the overhead MEP" / clash-free / from the drawing set | `output/solution.py`（单个可执行程序） |
| **寿命周期成本** | life cycle cost / replacement / alternatives | `.zip`（多套算稿 + dxf + 台账 + basis） |

**注意**：布线型交付的是**代码**，不是文档。grader 会跑它。所以这题的正确产出是"读图纸 → 建几何 → 布线 → 输出结构化结果"的程序，不是一份说明。

## 工作法

1. **版本冲突先解决**。MEP 题几乎都有"superseded 版本"陷阱（如 Rev A 把管线归 C4，Rev C 归 C5）。`design_basis.md` / `MOP.md` 第 2 节必须写明"以哪一版为准、为什么"。
2. **回路先定义，再算流量**。所有计算按 `circuit_id` 分桶，不允许跨回路合并。
3. **水力算三项**：流速、雷诺数、所需扬程 vs 可用扬程。三个都要进表，缺一个就没法核验。
4. **程序型题先跑通再优化**。solution.py 第 1 版要能 import 无错、能在样例输入上输出合法结构，再谈避让质量。

## 必需件与列头

### MOP 程序包
`MOP.md` + `flush_plan.csv` + `chemistry_plan.csv` + `acceptance_matrix.csv` + `schedule.csv` + `constraint_register.csv` + `resources.json`

| 文件 | 列头（照抄） |
|---|---|
| `flush_plan.csv` | `circuit_id,stage,skid_id,skids_parallel,flow_gpm,governing_segment,governing_id_in,velocity_fps,reynolds,required_head_ft,skid_head_avail_ft,duration_h` |
| `chemistry_plan.csv` | `circuit_id,stage,program,product_id,active_species,target_ppm,basis_volume_gal,product_quantity,product_unit,packages,ph_target_lo,ph_target_hi,hold_days,source` |
| `acceptance_matrix.csv` | `circuit_id,gate,parameter,method,sample_point_tag,threshold_op,threshold_value,units,basis_doc,basis_clause` |
| `schedule.csv` | `activity_id,circuit_id,stage,predecessor_ids,start_h,finish_h,skid_id,crew_id,water_draw_gal,attended_h,location` |
| `constraint_register.csv` | `id,document,clause,requirement,value,items_bound` |

`MOP.md` 章节：
```
0. Summary of the plan
1. Scope
2. Document basis
3. Circuit definition (read from the P&IDs, Rev X)
4. Design basis
 4.1 Volumes, flushing flow and governing segment
 4.2 Skid duty, head and power
 4.3 Hydrostatic testing
```

`resources.json`：`skid_assignment` 按 circuit → stage → skid 三级嵌套。

### 布线程序（solution.py）
- 入口可被外部调用，读图纸数据，输出路由结果（结构化 JSON / 表）
- 必须有：几何重建、冲突检测、避让排序
- 不要求 UI，不要求注释成文；要求**能跑、结果可解析**

### 寿命周期成本
每套 plant 一份 `*_CALC_*.xlsx`，工作表组固定：
```
DesignPoint / OffDesign / WaterBalance / Energy / LifeCycleCost
```
外加 `*_SCHEDULE_*.dxf`（设备排布）+ `constraint_register.csv` + `design_basis.md`

`design_basis.md` 章节：
```
1. Governing documents
2. Documented conflicts
3. Climatic and property basis
4. Calculation methods
5. Selected designs
6. Governing constraint per plant
7. Judgement calls and margins
```

## 常见死法

- 用 superseded 版图纸算 → 全部回路错位，连锁失分
- 只给最终流量，不给 governing segment 和雷诺数
- 多 plant 题只做一套算稿（三套是题面要求，漏一套丢三分之一）
- solution.py 靠硬编码题面坐标过关 → 违反反作弊
- chemistry_plan 的 `basis_volume_gal` 没跟 flush_plan 的体积对上
