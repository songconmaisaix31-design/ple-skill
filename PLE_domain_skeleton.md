# PLE dev-set 交付物骨架（29 题反推）

来源：`physical-engineerings-last-exam/submission-template` 的 `artifacts/`，即 Pi 1.1.0 + Claude Opus 5.5 在 29 个 dev 任务上的真实产出。
用途：每个 domain 的 skill 施工图。只取**格式惯例**，不取题目答案。


## electrical（7 题）

| 任务 | 交付形态 | 标题 |
|---|---|---|
| `backfeed-energization-reply` | docx | — |
| `data-hall-device-takeoff` | zip | Device takeoff and priced bill of materials for a data hall -- ec_0205 |
| `division-26-specifications` | zip | Building 4410: Division 26 project specifications (final submittal) |
| `lv-cable-sizing` | zip | Low-voltage wire schedule — Building 4210, Consolidated Support Facili |
| `pre-application-capacity-response` | docx | — |
| `solar-supplemental-review` | docx | — |
| `solar-witness-test-package` | docx | — |

### 交付规格明细

#### `backfeed-energization-reply`
- docx `filesystem/Halbray_Backfeed_Reply.docx`
  - 疑似章节：ALLENIOM UTILITIES — DER PROGRAM OFFICE / 07/14/2025 / Ms. Imogen Strathe / Project Manager / Halbray Community Solar LP / 6120 Halbray Road / Kelloway Township, Alleron 07KT / Our answer / 1.  The permit condition / 2.  Code items in the construction records / 3.  What has to be done before 07/29/2025, and by whom / 4.  During the backfeed
  - 表格列头：[['#', 'What the schedules show', 'NEC 2023 requirement', 'What has to be done'], ['Step', 'Action', 'By whom', 'When']]
- 收尾摘要写法：I've drafted the reply letter and opened one OpenProject work package (#47). The letter tells Ms. Strathe that, as the records stand at 07/14/2025, we cannot energize Site 3 on 07/

#### `data-hall-device-takeoff`
- 交付路径：`/filesystem/final_batch4__electrical_task17_ec_0205_d100__blind/output/submission.zip`
- zip 内部（5 项）：
  - `basis.md`
  - `bom.csv`
  - `locations.csv`
  - `register.csv`
  - `takeoff.csv`
  - **CSV 列头** `bom.csv`：line_item,description,for_type_mark,condition,quantity,unit,unit_price,extended_price
  - **CSV 列头** `locations.csv`：sheet,type_mark,grid_bay,condition,count
  - **CSV 列头** `register.csv`：family,document,clause,value,how_satisfied
  - **CSV 列头** `takeoff.csv`：type_mark,description,quantity
  - **MD 章节** `basis.md`：BASIS OF ESTIMATE - DATA HALL 1 DEVICE TAKEOFF AND PRICED BI / 1. Counting conventions applied / 2. Sheets each type mark was counted from, and the takeoff / 3. Governing issue, addendum and keyed notes / 4. Unresolved symbols (not in the E-001 legend - no quantity / 5. Condition split and where it came from / 6. Assembly chosen for each (type mark, condition) pair and  / 7. Pricing, spare stock and cartons / 8. Grid bays and coordinates
- 收尾摘要写法：**How I counted.** I matched every symbol on the plans against the 17 symbols in the E-001 legend, then placed each one on the hall floor grid using the tile lines printed on each 

#### `division-26-specifications`
- 交付路径：`design_basis.xlsx`
- zip 内部（7 项）：
  - `design_basis.xlsx`
  - `specs/26 05 73.docx`
  - `specs/26 20 00.docx`
  - `specs/26 24 13.docx`
  - `specs/26 32 15.docx`
  - `specs/26 36 23.docx`
  - `specs/26 51 00.docx`
  - 嵌套 xlsx `design_basis.xlsx` sheets=['Sections', 'Feeders', 'ShortCircuit', 'Photometric', 'BuildingLPD', 'StepLoad', 'StepLoadCheck', 'CumulativeVD', 'Register', 'Findings'] 首行串=[]
  - 嵌套 `specs/26 05 73.docx`：tables=[] heads=[]
  - 嵌套 `specs/26 20 00.docx`：tables=[['Feeder', 'From', 'To', 'Conductors (copper, XHHW-2)', 'Raceway'], ['Panelboard', 'Voltage', 'Calculated available fault current (kA)', 'Minimum short-circuit current rating (rm']] heads=[]
  - 嵌套 `specs/26 24 13.docx`：tables=[] heads=[]
  - 嵌套 `specs/26 32 15.docx`：tables=[['Parameter', 'Requirement'], ['Step', 'Loads', 'Starting kVA', 'Running kVA before step', 'Calculated voltage dip (percent)', 'Calculated recovery time (seconds)'], ['Voltage droop percent =', '(No-Load Volts) - (Rated Capacity Volts)', 'x 100']] heads=[]
  - 嵌套 `specs/26 36 23.docx`：tables=[] heads=[]
  - 嵌套 `specs/26 51 00.docx`：tables=[['Luminaire Style', 'Minimum Luminaire Efficacy'], ['Space', 'Room name', 'Type', 'Quantity', 'Layout']] heads=[]
- 收尾摘要写法：**Choices that could cost credit:** / - **Generator step-load uses 3 steps, not 2.** GSB-01's own rules allow a 2-step sequence. But IES-26 10.6 and GLC-01 have ATS-E transferring 

#### `lv-cable-sizing`
- 交付路径：`output/submission.zip`
- zip 内部（5 项）：
  - `E-621_wire_schedule.dxf`
  - `calc_book.xlsx`
  - `constraint_register.xlsx`
  - `design_basis.md`
  - `wire_schedule.csv`
  - **CSV 列头** `wire_schedule.csv`：circuit,description,from,to,install_class,length_ft,sets,size,material,egc_size,raceway_trade_in,duct_ids,design_current_a,corrected_ampacity_a,vd_load_a,vd_pct
  - **MD 章节** `design_basis.md`：Design basis - low-voltage wire schedule, sheet E-621, proje / 1. Codes of record, adopting document, order of precedence / 2. Environmental parameters and provenance / 3. Load basis and ampacity method / 4. Service-entrance sizing decision / 5. Voltage-drop budget allocation / 6. Duct-bank assignment and thermal consequence / 7. Material and standardisation decisions / 8. Cost ledger - material and labour
  - 嵌套 xlsx `calc_book.xlsx` sheets=['front_sheet', 'duct_assignment', 'cost_ledger'] 首行串=[]
  - 嵌套 xlsx `constraint_register.xlsx` sheets=['register'] 首行串=[]
- 收尾摘要写法：**What the design rests on** / - **Codes of record:** NFPA 70 2023 and IBC 2024, adopted through UFC 1-200-01; where documents disagree, the most restrictive requirement governs (s

#### `pre-application-capacity-response`
- docx `filesystem/ALN-108_PreApplication_Response.docx`
  - 标题：H?:Part A — Response letter (for issue) / H?:1.  Available capacity on Feeder ALN-108 / H?:2.  Known conditions, restrictions and upgrade indications / H?:3.  Refreshed figure and pre-application meeting / H?:Part B — Determinations and basis / H?:D1.  The published 3.0 MW figure is not confirmed as current / H?:D2.  The response carries 0.8 MW as the indicative available capacity / H?:D3.  The 10/15/2024 interim figure of 1.8 MW is superseded / H?:D4.  Capacity cannot be confirmed for the 3 MW project; the gap and the options  / H?:D5.  The response is indicative and non-binding
  - 疑似章节：ALLENIOM UTILITIES — DER PROGRAM OFFICE / Feeder ALN-108 — Pre-Application Response / The call / Contents / Part A — Response letter, for issue to the requester / Part B — Determinations and the basis relied on (D1–D8, and the call) / Annex A — ALN-108 queue entries and the netting calculation / Annex B — Records reviewed / ALLENIOM UTILITIES / DER Program Office / July 14, 2025 / By email: peter.ashford@northlinerenewables.com
  - 表格列头：[['Item', 'Detail'], ['NOT CONFIRMED. The DER Program Office do'], ['Queue date', 'Nameplate', 'Stage at 07/14/2025'], ['Indicative available capacity, Feeder AL'], ['#', 'Question', 'Determination']]
- 收尾摘要写法：The 3.0 MW figure can't be confirmed. The response gives Northline **0.8 MW** as the indicative available capacity on ALN-108 as of 07/14/2025, and tells them their 3 MW project is

#### `solar-supplemental-review`
- docx `filesystem/Bramwick_Commons_Screen_Memo.docx`
  - 疑似章节：Alleniom Utilities — DER Program Office / SUPPLEMENTAL REVIEW SCREEN DETERMINATION — SUPERSEDING MEMO / Issued under SRP-3 Rev 3 §4 (final paragraph) and §6 / To:Meera Vellanki, Manager, Interconnection Studies / Date:07/14/2025 / Determination summary / 1. Application (SRP-3 §6(a)) / 2. Why this memo is issued / 3. Determinations, basis, and call / 4. Screen D worksheet summary (SRP-3 §6(c)) / v1 compared with this memo / 5. Screens applied and determinations (SRP-3 §6(b))
  - 表格列头：[['Doc no.', 'Rev', 'Date', 'Owner', 'Supersedes'], ['Screen D — 100%-of-minimum-load (solar),', 'PASS  —  1.8 MW requested ≤ 2.4 MW dayti'], ['Application identifier', 'Not stated on v1. Bramwick Commons Solar'], ['No.', 'Question', 'Call', 'Basis relied on'], ['Subject feeder', 'ALN-214']]
- 收尾摘要写法：I've written the superseding memo of record (IS-BRAM-2025-07-14 v2). It reverses the earlier memo: Bramwick Commons now **passes** the minimum-load screen, so the disposition is **

#### `solar-witness-test-package`
- 收尾摘要写法：Now the case tracking in OpenProject. Let me check API access.


## structural（8 题）

| 任务 | 交付形态 | 标题 |
|---|---|---|
| `eor-review-corrections` | zip | Issue the EOR review corrections: Fleet Data Center Increment 2, work  |
| `footing-settlement-verification` | docx | — |
| `foundation-strategy` | zip | Cattail Run Data Campus — Phase 1 foundation strategy: spread footings |
| `frame-extension-method` | zip | Frame extension over an occupied floor — the method package |
| `roof-deck-design` | zip | DC-2 Helena data centre — roof deck design for gravity and lateral loa |
| `seismic-diaphragm-shear` | zip | Building B — seismic diaphragm shears and shear wall loads |
| `shoring-design-verification` | docx | — |
| `wind-diaphragm-shear` | zip | Building A2 — roof diaphragm shears and shear wall loads for wind |

### 交付规格明细

#### `eor-review-corrections`
- 交付路径：`constraint_register.xlsx`
- zip 内部（7 项）：
  - `constraint_register.xlsx`
  - `continuation_sheet.md`
  - `design_basis.md`
  - `disposition_register.csv`
  - `issue_plan.csv`
  - `revision_log.csv`
  - `sheet_index.csv`
  - **CSV 列头** `disposition_register.csv`：PACKAGE,COMMENT_ID,AUTHOR,SIGNIFICANCE,VALIDITY,VOID_REASON,RESPONSE,RESOLUTION,PRIMARY_SHEET,PRIMARY_VIEW,CHANGE_KIND,SHEETS_CHANGED,SHEETS_IMPACTED,CLOSURE
  - **CSV 列头** `issue_plan.csv`：PACKAGE,BUNDLE_ID,BUNDLE_FILE,SHEET_NUMBER,DISCIPLINE_DESIGNATOR,PLOT_PDF_MB,BUNDLE_SEQ
  - **CSV 列头** `revision_log.csv`：PACKAGE,SHEET_NUMBER,MARK,DESCRIPTION,DATE,ROW_POSITION,OVERFLOW_OPTION
  - **CSV 列头** `sheet_index.csv`：PACKAGE,INDEX_ORDER,SHEET_NUMBER,SHEET_NAME,CURRENT_REVISION,ISSUE_ACTION,IN_THIS_ISSUE
  - **MD 章节** `continuation_sheet.md`：Change documentation for the Contracting Officer - Work Orde / BP-2 Central Utility Plant and Site Utilities - Solicitation / BP-3 Data Hall 210 Shell and Interiors - Solicitation N40085
  - **MD 章节** `design_basis.md`：Design basis - EOR review corrections, Work Order 74213 (BP- / A. Documents that govern, and why / B. Which markups can direct a change / C. What each surviving comment does / D. What an accepted change drags in / E. (a) Revision-graphics layers / F. (b) BP-3 issue state, dates and review window / G. BP-2 amendment, window and schedule / H. (c) BP-2 Revision (Issue) block overflow
  - 嵌套 xlsx `constraint_register.xlsx` sheets=['CONSTRAINT REGISTER'] 首行串=[]
- 收尾摘要写法：**What the plan decides** / | | BP‑2 | BP‑3 | / |---|---|---| / | Issue state | Amendment 0003 (already advertised, so the only lawful course) | Re‑issue before advertisement |

#### `footing-settlement-verification`
- docx `filesystem/Thelbridge_Verification_Memo_Item051_BlockC.docx`
  - 疑似章节：THELBRIDGE PROJECT MANAGEMENT SERVICES / VERIFICATION MEMORANDUM / From:Rahul Nimkar, Geotechnical Reviewer / Date:07/20/2026 / 1.  PURPOSE / 2.  DOCUMENTS REVIEWED / 3.  BASIS OF REVIEW / 3.1  Governing requirements / 3.2  Review method / GIR §8.1 form:   Sc = Cc · H/(1 + e0) · log10[(σ'0 + Δσ) / σ'0] / 4.  FINDINGS / 5.  CONCLUSION AND RECOMMENDATION
  - 表格列头：[['Ref.', 'Document', 'Revision / identifier', 'Date'], ['Case', "σ'0 (psf)", 'Δσ at mid-clay (psf)', 'Sc (in) 1'], ['No.', 'To be produced', 'Required of', 'Timing']]
- docx `filesystem/Thelbridge_Verification_Memo_TEMPLATE_v1.docx`
  - 疑似章节：THELBRIDGE PROJECT MANAGEMENT SERVICES / VERIFICATION MEMORANDUM / 1.  PURPOSE / 2.  DOCUMENTS REVIEWED / 3.  BASIS OF REVIEW / 4.  FINDINGS / 5.  CONCLUSION AND RECOMMENDATION / Name / Title / Thelbridge Project Management Services - Owner's Representative / Date
- 收尾摘要写法：The Item 051 memo is written on your template, from Rahul Nimkar to Adrian Vance, cc Rachel Marlbeck, dated 07/20/2026. The disposition is **NOT VERIFIED** and the item stays **Ope

#### `foundation-strategy`
- 交付路径：`output/submission.zip`

#### `frame-extension-method`
- 交付路径：`output/submission.zip`
- zip 内部（6 项）：
  - `constraint_register.csv`
  - `construction_sequence.csv`
  - `method_note.md`
  - `occupancy_report.csv`
  - `stability_check.csv`
  - `temporary_works.json`
  - **CSV 列头** `constraint_register.csv`：requirement,document,clause,value,unit,items_bound,description,applied_as
  - **CSV 列头** `construction_sequence.csv`：activity_id,zone,level,activity_type,predecessors,duration_days,start_day,finish_day,crew,crane_hours,workspace_volume_cf,gang_id,daily_crane_draw,volume_basis,
  - **CSV 列头** `occupancy_report.csv`：zone_lift,zone,level,occupied_from_day,occupied_to_day,shored_from_day,shored_to_day,crane_hours_total,laydown_units,staging_start,staging_end,scaffold_erect_st
  - **CSV 列头** `stability_check.csv`：stage_id,zone,level,lateral_system,demand_lb,capacity_lb,verdict,wind_case,notional_case,vertical_load_supported,governing_case,xb1_bays,adjacent_slab,shoring_u
  - **MD 章节** `method_note.md`：Method note - frame extension over the occupied ground floor / 1. Which document governs where the issued set disagrees wit / 2. Striking and reshoring method adopted / 3. Programme / 4. The constraint that governs each zone / 5. Temporary works design / 6. Margins applied / 7. Attribution
  - `temporary_works.json`：<json> {  "designer": "R. Castellan, P.E. - Temporary Works Designer for the frame extension (qualified person, 29 CFR 1
- 收尾摘要写法：**What's in it** / - **`construction_sequence.csv`**: all 294 issued activities with their issued durations, links and crane hours. Work starts on day 0, the last activity finishes

#### `roof-deck-design`
- 交付路径：`output/submission.zip`
- zip 内部（4 项）：
  - `constraint_register.xlsx`
  - `deck_design.xlsx`
  - `design_basis.md`
  - `roof_deck_plan.dxf`
  - **MD 章节** `design_basis.md`：DC-2 Helena Data Centre, Building A - Roof Deck Design Basis / 1. Governing documents and how conflicts were resolved / 2. Snow basis / 3. Wind uplift basis / 4. Seismic basis / 5. Diaphragm analysis and classification / 6. Zoning decisions / 7. Coordination items
  - 嵌套 xlsx `constraint_register.xlsx` sheets=['Register'] 首行串=[]
  - 嵌套 xlsx `deck_design.xlsx` sheets=['Zones', 'DesignBasis', 'Drifts', 'CalcSummary', 'Diaphragm', 'BOM'] 首行串=[]
- 收尾摘要写法：**Design: 3 zones, 14 rectangles, 2 gages (18 and 22), 3 attachment patterns** / | Zone | Where | Gage / pattern / sidelaps | What drove it | / |---|---|---|---| / | Z01 | West str

#### `seismic-diaphragm-shear`
- 交付路径：`constraint_register.xlsx`
- zip 内部（5 项）：
  - `constraint_register.xlsx`
  - `design_basis.md`
  - `design_record.json`
  - `diaphragm_plan.dxf`
  - `seismic_calculations.xlsx`
  - **MD 章节** `design_basis.md`：Building B - seismic diaphragm and shear wall design basis / 1. Seismic basis / 2. Seismic force-resisting system / 3. As-built geometry / 4. Analysis / 5. Diaphragm and wall forces / 6. Wall anchorage and the parapet cantilever / 7. Governing constraint per wall line / 8. Cost
  - `design_record.json`：<json> {  "sfrs": "intermediate_precast",  "design_format": "LRFD",  "diaphragm_method": "ASCE/SEI 7-22 Sections 12.10.1
  - 嵌套 xlsx `constraint_register.xlsx` sheets=['CONSTRAINT REGISTER'] 首行串=[]
  - 嵌套 xlsx `seismic_calculations.xlsx` sheets=['WEIGHTS', 'BASE_SHEAR', 'DIAPHRAGM_FORCES', 'WALL_FORCES', 'PARAPET_ANCHORAGE', 'CHORD_FORCES'] 首行串=[]
- 收尾摘要写法：**Design (strength design, LRFD throughout)** / - **Wall system:** intermediate precast shear walls (UFC 3-301-01 Table 3-1 row A.6), R = 4, Ω0 = 2.0 (2.5 reduced by 0.5 for the fl

#### `shoring-design-verification`
- docx `filesystem/Thelbridge_Verification_Memo_Item048_BlockB.docx`
  - 疑似章节：THELBRIDGE PROJECT MANAGEMENT SERVICES / VERIFICATION MEMORANDUM / Date:07/20/2026 / 1.  PURPOSE / 2.  DOCUMENTS REVIEWED / 3.  BASIS OF REVIEW / 3.1  Object and nature of the review / 3.2  Governing requirements / 3.3  Logged conditions applied / 3.4  Method / 4.  FINDINGS / 4.1  Groundwater and stratigraphy inputs agree with the logged record
  - 表格列头：[['Tag', 'Document', 'Date'], ['su (psf)', 'pn = 4su − σv0 (psf)', 'Pp over D = 6.5 ft (lb/ft)', 'MR about El. 745.5 (ft-lb/ft)', 'FS (1.50 required)'], ['Rev.1 §', 'Title and status given in R2 Table 1', 'What R1 actually contains (page)'], ['Check or provision', 'Where', 'Carry forward as it stands?', 'Reason'], ['No.', 'To be produced', 'By', 'Minimum content']]
- docx `filesystem/Thelbridge_Verification_Memo_TEMPLATE_v2.docx`
  - 疑似章节：THELBRIDGE PROJECT MANAGEMENT SERVICES / VERIFICATION MEMORANDUM / 1.  PURPOSE / 2.  DOCUMENTS REVIEWED / 3.  BASIS OF REVIEW / 4.  FINDINGS / 5.  CONCLUSION AND RECOMMENDATION / Name / Title / Thelbridge Project Management Services - Owner's Representative / Date
- 收尾摘要写法：I've written and saved the verification memo, addressed to Rachel Marlbeck on the house form with its five sections and signature block kept. Its disposition is **NOT VERIFIED**: I

#### `wind-diaphragm-shear`
- 交付路径：`constraint_register.xlsx`
- zip 内部（5 项）：
  - `calculations.pdf`
  - `constraint_register.xlsx`
  - `design_basis.md`
  - `diaphragm_plan.dxf`
  - `lateral_schedule.xlsx`
  - **MD 章节** `design_basis.md`：Design Basis - Building A2 Roof Diaphragm, Chords, Collector / 1. Values the design was built on / 2. Governing wind scenario for each wall line / 3. Conflicts between issued documents and how they were reso / 4. Load basis / 5. Analysis / 6. Design summary
  - 嵌套 xlsx `constraint_register.xlsx` sheets=['Register'] 首行串=[]
  - 嵌套 xlsx `lateral_schedule.xlsx` sheets=['DeckZones', 'ChordSchedule', 'Piers', 'ShearWalls', 'Diaphragm', 'Chords', 'Drift', 'Convergence', 'Cost'] 首行串=[]
- 收尾摘要写法：The zip has the five required files: the nine-sheet `lateral_schedule.xlsx`, `diaphragm_plan.dxf`, `constraint_register.xlsx` (116 rows), a 19-sheet letter-portrait `calculations.p


## mep（4 题）

| 任务 | 交付形态 | 标题 |
|---|---|---|
| `cooling-water-flush-plan` | zip | Process cooling water cleaning, flushing and passivation — Tull Creek  |
| `data-hall-mep-routing` | file | Route the overhead MEP of a data hall from its drawing set, clash-free |
| `data-hall-mep-routing-offset` | ? | — |
| `heat-rejection-life-cycle-cost` | zip | Condenser water heat rejection replacement — Papago Federal Center, Ph |

### 交付规格明细

#### `cooling-water-flush-plan`
- 交付路径：`/filesystem/final_batch4__mechanical_task5_pcw_flush_mop__blind/output/submission.zip`
- zip 内部（7 项）：
  - `MOP.md`
  - `acceptance_matrix.csv`
  - `chemistry_plan.csv`
  - `constraint_register.csv`
  - `flush_plan.csv`
  - `resources.json`
  - `schedule.csv`
  - **CSV 列头** `acceptance_matrix.csv`：circuit_id,gate,parameter,method,sample_point_tag,threshold_op,threshold_value,units,basis_doc,basis_clause
  - **CSV 列头** `chemistry_plan.csv`：circuit_id,stage,program,product_id,active_species,target_ppm,basis_volume_gal,product_quantity,product_unit,packages,ph_target_lo,ph_target_hi,hold_days,source
  - **CSV 列头** `constraint_register.csv`：id,document,clause,requirement,value,items_bound
  - **CSV 列头** `flush_plan.csv`：circuit_id,stage,skid_id,skids_parallel,flow_gpm,governing_segment,governing_id_in,velocity_fps,reynolds,required_head_ft,skid_head_avail_ft,duration_h,circuit_
  - **CSV 列头** `schedule.csv`：activity_id,circuit_id,stage,predecessor_ids,start_h,finish_h,skid_id,crew_id,water_draw_gal,attended_h,location
  - **MD 章节** `MOP.md`：Method of Procedure - PCW Cleaning, Flushing, Passivation an / 0. Summary of the plan / 1. Scope / 2. Document basis / 3. Circuit definition (read from the P&IDs, Rev C) / 4. Design basis / 4.1 Volumes, flushing flow and governing segment / 4.2 Skid duty, head and power / 4.3 Hydrostatic testing
  - `resources.json`：<json> {  "skid_assignment": {   "C1": {    "INITIAL_FLUSH": {     "skid_id": "FS-1200-A",     "skids_parallel": 1,     
- 收尾摘要写法：**The engineering** / - **Circuits:** read from the current (Rev C) P&IDs. The superseded M-PID-103 Rev A puts line 4033 in C4; Rev C moves it to C5, and that line then sets C5's f

#### `data-hall-mep-routing`
- 交付路径：`output/solution.py`
- 收尾摘要写法：**Background, rebuilt from the drawings** (overlaid on M-101, E-101 and F-101, everything lines up): / - **Racks:** 128 placed from the bay sequences starting at tile D (x = 1800).

#### `data-hall-mep-routing-offset`
- 收尾摘要写法：**The main design decision: everything runs under the floor.** The sprinkler deflectors sit at +3024.6, and keeping 460 mm clear below them means nothing can go above +2564.6. That

#### `heat-rejection-life-cycle-cost`
- 交付路径：`output/submission.zip`
- zip 内部（8 项）：
  - `CT_CALC_ANNEX.xlsx`
  - `CT_CALC_CUP.xlsx`
  - `CT_CALC_LAB.xlsx`
  - `CT_SCHEDULE_ANNEX.dxf`
  - `CT_SCHEDULE_CUP.dxf`
  - `CT_SCHEDULE_LAB.dxf`
  - `constraint_register.csv`
  - `design_basis.md`
  - **CSV 列头** `constraint_register.csv`：id,document,clause,requirement,value,items_bound
  - **MD 章节** `design_basis.md`：Design basis - condenser water heat rejection replacement, P / 1. Governing documents / 2. Documented conflicts (DC-02 9.1) / 3. Climatic and property basis / 4. Calculation methods / 5. Selected designs / 6. Governing constraint per plant (DC-02 9) / 7. Judgement calls and margins
  - 嵌套 xlsx `CT_CALC_ANNEX.xlsx` sheets=['DesignPoint', 'OffDesign', 'WaterBalance', 'Energy', 'LifeCycleCost'] 首行串=[]
  - 嵌套 xlsx `CT_CALC_CUP.xlsx` sheets=['DesignPoint', 'OffDesign', 'WaterBalance', 'Energy', 'LifeCycleCost'] 首行串=[]
  - 嵌套 xlsx `CT_CALC_LAB.xlsx` sheets=['DesignPoint', 'OffDesign', 'WaterBalance', 'Energy', 'LifeCycleCost'] 首行串=[]
- 收尾摘要写法：## Selected designs / | | CUP | ANNEX | LAB | / |---|---|---|---| / | Cells | 4 × CTX‑0600‑S | 4 × CTX‑0600‑S | 3 × CTX‑0900‑H |


## civil（4 题）

| 任务 | 交付形态 | 标题 |
|---|---|---|
| `emergency-spillway-check` | docx | — |
| `fill-compaction-acceptance` | docx | — |
| `landscape-sheet-revision` | file | Where to put your answer |
| `mv-conveyance-study` | zip | Pacific Crest Space Force Annex — conveyance study for the 13.8 kV sit |

### 交付规格明细

#### `emergency-spillway-check`
- docx `filesystem/Memo_to_Callaway_Spillway_2026-10-31.docx`
  - 疑似章节：SUNDIAL ENGINEERING & SURVEY / MEMORANDUM / 1.  Purpose and Bottom Line / 2.  Dispositions / 3.  The Spillway as Drawn / 4.  Amendment to the Accepted Master Drainage Study / 5.  The Revised Sheet C-9 / 5.1  Design basis (stated on the sheet and in the calculation package) / 5.2  Spillway detail — values / 5.3  Spillway detail — section and erosion protection / 5.4  Basin notes / 5.5  Consequential edits in the same revision
  - 表格列头：[['TO:', 'Garrett Nokes, Vice President, Land Deve'], ['No.', 'Question', 'Disposition'], ['Disposition 1 — No. G-4 cannot be answer'], ['Parameter', 'Accepted MDS (source)', 'Revised C-9 (this memo)', 'Preliminary calc, 09/25/2026 (cell)'], ['Disposition 2 — No amendment. The C-9 re']]
- 收尾摘要写法：I've saved the memo at `/filesystem/Memo_to_Callaway_Spillway_2026-10-31.docx`, dated 10/31/2026 and addressed to Garrett Nokes. It runs 13 pages: a 7-page memo plus Attachments A 

#### `fill-compaction-acceptance`
- xlsx `filesystem/Fill_Placement_Records_BlockA_SlabOnGrade.xlsx` sheets=['Cover', 'Daily Placement Log', 'Notes', 'Signature'] 串=[]
- docx `filesystem/Thelbridge_Materials_Acceptance_Fill_Compaction_2026-0708.docx`
  - 疑似章节：THELBRIDGE PROJECT MANAGEMENT SERVICES / MATERIALS ACCEPTANCE RECORD / From:Karen Tarbray, Materials / QA Reviewer / Date:07/15/2026 / 1.  PURPOSE / 2.  DOCUMENTS REVIEWED / 3.  BASIS OF REVIEW / 4.  FINDINGS / 5.  CONCLUSION AND RECOMMENDATION / Determination: REJECTED / Karen Tarbray / Materials / QA Reviewer
  - 表格列头：[['#', 'Document', 'Date', 'Cited as'], ['Article (Spec page)', 'Requirement applied in this review'], ['Criterion', 'Derivation (P04: 128.4 pcf at 9.2%)', 'Acceptance limit'], ['Test', 'Location(Lift 6, El. 748.6)', 'Dry density(pcf)', '% of128.4 pcf', 'Density≥ 122.0 pcf', 'Moisture(%)', 'Deviationfrom 9.2%', 'Moisture8.2–11.2%', 'Result against P04'], ['Requirement (Article; Spec page)', 'What the record shows', 'Status']]
- docx `filesystem/Thelbridge_Materials_Acceptance_Record_TEMPLATE.docx`
  - 疑似章节：THELBRIDGE PROJECT MANAGEMENT SERVICES / MATERIALS ACCEPTANCE RECORD / 1.  PURPOSE / 2.  DOCUMENTS REVIEWED / 3.  BASIS OF REVIEW / 4.  FINDINGS / 5.  CONCLUSION AND RECOMMENDATION / Name / Title / Thelbridge Project Management Services - Owner's Representative / Date
- 收尾摘要写法：The record is saved to `/filesystem/Thelbridge_Materials_Acceptance_Fill_Compaction_2026-0708.docx` (7 pages, house template). **The determination is REJECTED for all four tests (F

#### `landscape-sheet-revision`
- 交付路径：`output/`
- docx `app/files/output/DSR_Ph3_L-4_Street_Tree_Memo_to_Callaway_2026-10-31.docx`
  - 疑似章节：SUNDIAL ENGINEERING & SURVEY / MEMORANDUM / 1.  Bottom line / 2.  What has to happen first / 3.  Why each item controls the date / – the 10-ft P.U.E. across all lot frontages on our final map; / – joint-trench lateral JT-B along the east side of Desert Sage Pkwy.; / – an unplotted 1989 LVVWD transmission easement (exception 8); and / 4.  Why 11/30 is the outside date, not the target / 5.  Cost and bond / 6.  What I need from you / the frontage tabulation and the shade-coverage exhibit;
  - 表格列头：[['TO:', 'Garrett Nokes, Vice President, Land Deve'], ['#', 'What has to happen', 'Why it controls the date', 'Owner', 'Need by'], ['Park program', 'Street trees', 'Turf', 'Drip', 'Trees (all)', 'Total ac-ft/yr']]
- 收尾摘要写法：The memo to Garrett is drafted for your signature, dated 10/31/2026. Short answer: we can't commit to 11/30 for the L-4 revision today. The drafting itself fits, but four things ou

#### `mv-conveyance-study`
- 交付路径：`output/submission.zip`
- zip 内部（2 项）：
  - `conveyance_study.xlsx`
  - `conveyance_study_report.md`
  - **MD 章节** `conveyance_study_report.md`：Conveyance Study - 13.8 kV Site Distribution, Pacific Crest  / 1. Summary of recommendations / 2. Estimating basis / Labor rates used / Crew rates used / Equipment rates used / Material unit rates used (installed price incl. waste, index / Labor units used (MH per unit after conversions) / 3. Item studies
  - 嵌套 xlsx `conveyance_study.xlsx` sheets=['Items', 'Segments', 'Structures', 'Pulls', 'Alternatives', 'Takeoff', 'LaborRates', 'EquipmentRates', 'Markups', 'Register', 'Findings'] 首行串=[]
- 收尾摘要写法：| Item | Recommended | Cable | Route (ft) | Total project cost | / |---|---|---|---|---| / | C01 | Concrete-encased ductbank (CEDB) | 2 × 500 kcmil | 834 | $262,930 | / | C02 | CED


## fire（2 题）

| 任务 | 交付形态 | 标题 |
|---|---|---|
| `fire-solve-convergence` | docx | — |
| `fire-test-validation-memo` | file | Where to put your answer |

### 交付规格明细

#### `fire-solve-convergence`
- docx `filesystem/CFDME-2025-041_transient_solve_disposition_revA.docx`
  - 标题：H?:1.  Disposition / H?:2.  Record Reviewed / H?:3.  The Residual Plateau / H?:3.1  What the plume should show / H?:3.2  What attempt 3 showed / H?:3.3  How close they are / H?:3.4  Reading / H?:4.  Steady Solution and the Delivered Setup / H?:4.1  No steady solution exists / H?:4.2  Delivered setup against the standards
  - 疑似章节：TECHNICAL NOTE / f = 1.5 · D−1/2 = 1.5 × (3.0 m)−1/2= 0.87 Hz(0.8660 Hz unrounded) / T = 1 / f= 1.15 s(1.1547 s unrounded) / applicationfireFoam; / startFromlatestTime; / startTime0;// s / stopAtendTime; / endTime31.10;// s = 8.00 s startup + 20 × 1.1547 s, rounded up / deltaT0.001;// s, initial step; adapted thereafter / writeControladjustableRunTime; / writeInterval0.0461;// s simulated; 25.05 samples per 1.1547 s period / purgeWrite0;// keep all time directories
  - 表格列头：[['Project:', 'CFDME-2025-041 — Ocotillo WUI Wildfire, '], ['Item', 'Disposition'], ['Record', 'File', 'Originator'], ['Quantity', 'Frequency', 'Period'], ['Item', 'Delivered (bundle; attempt-3 log)', 'Status', 'Shall be']]
- 收尾摘要写法：I've saved the technical note to `/filesystem/CFDME-2025-041_transient_solve_disposition_revA.docx`. It's 10 pages on the firm letterhead, dated 10/10/2025, with the reviewer and s

#### `fire-test-validation-memo`
- 交付路径：`output/`
- docx `app/files/output/CFDME-2025-041_E119_validation_memo_revA.docx`
  - 疑似章节：MEMORANDUM / Validation of the ASTM E119 companion simulation — Phase 1 report §7 / 1. Bottom line / Rollup in the order Procedure §3 requires / 2. Sources / 3. Is the assembly in the run the one Ironwood certified? / Table 1 — Certified geometry, drawing and run geometry / 4. Governing criterion and when it is reached / Table 2 — Crossing times / 5. Experimental value and the amended figure / 6. Rollup: error, criterion and uncertainty / Table 3 — Rollup in Procedure §3 order
  - 表格列头：[['To', 'Marguerite Falk, PE — Technical Director'], ['S (companion run)', 'D (certified test)', 'E = S − D', 'u_val'], ['Role', 'Document', 'Identifier / location'], ['Parameter', 'Certified: IWFPE-CERT-25-0374 §1.2(= RBF', 'Drawing OAS-WA-305mm-DW Rev A', 'Run geometry OAS-WUI-01_revC'], ['Criterion', 'Limit (rise)', 'Test, RBFMT-25-0918 §5', 'Run crossing', 'Bracketing run samples']]
- 收尾摘要写法：I've written the validation memo as a Word document, addressed from you to Marguerite. The short answer for Bianca is no: against the certified test, the companion run is 13 min lo


## cost（1 题）

| 任务 | 交付形态 | 标题 |
|---|---|---|
| `engineers-estimate-check` | docx | — |

### 交付规格明细

#### `engineers-estimate-check`
- docx `filesystem/Correspondence/Client/Memo_to_Callaway_2026-10-31.docx`
  - 疑似章节：SUNDIAL ENGINEERING & SURVEY / MEMORANDUM / 1.  Summary / 2.  Basis of the check / 3.  Quantity and unit-price changes (Table 1) / Notes to Table 1 / 5.  Corrected Section 2 and bond figure (Table 3) / Lines confirmed or carried without change / 6.  What could still move Section 2 / ______________________________ / Max Braddock / Project Manager, Sundial Engineering & Survey
  - 表格列头：[['TO:', 'Garrett Nokes, Vice President, Land Deve'], ['', 'Rev. 0 (10/10/2026)', 'Corrected', 'Change'], ['No.', 'Item', 'Description', 'Sheet', 'Rev. 0', 'Corrected', 'Change'], ['Item', 'What the plans show (sheet)', 'Closest Schedule items', 'Left in subtotal'], ['Item', 'Description', 'Qty', 'Unit', 'Unit price', 'Amount', 'Status']]
- 收尾摘要写法：I've written the memo to Garrett for your signature. The corrected Section 2 subtotal is **$1,309,439**, up $32,505 from $1,276,934, and the revised bond figure is **$5,390,000** i


## bim（1 题）

| 任务 | 交付形态 | 标题 |
|---|---|---|
| `data-center-site-model` | file | Design a phased data-center campus on a wetland-divided greenfield par |

### 交付规格明细

#### `data-center-site-model`
- 交付路径：`python3 oracle_client.py submission/model.ifc`
- 收尾摘要写法：**Layout** (everything sits in the northern area, which keeps both medium-voltage cable and road short): / - **Road:** a 6 m road enters from the south frontage at (181, 0.5), runs


## cfd（1 题）

| 任务 | 交付形态 | 标题 |
|---|---|---|
| `les-mesh-resolution` | docx | — |

### 交付规格明细

#### `les-mesh-resolution`
- docx `filesystem/CFDME-2025-041_resolution_note_revA.docx`
  - 疑似章节：NOTE — CHECKLIST ITEM 4: LES RESOLUTION BASIS / Bottom line / 1.  Where the plume resolution index lands / Table 1 — Plume resolution index, study fine grid / 2.  What the acceptance rests on, and what needs Marguerite / 3.  Was the 84 % taken inside the region the index describes? / 4.  Do the ambient values behind D* represent the site? / 5.  Can item 4 close?
  - 表格列头：[['To:', 'Marguerite Falk, PE — Technical Director'], ['D* basis', 'D*', 'D*/dx, fire zone(dx = 0.125 m)', 'D*/dx, background(dx = 0.5 m)']]
- 收尾摘要写法：I've written the note: `/filesystem/CFDME-2025-041_resolution_note_revA.docx` (about 2¼ pages). Item 4 can't close on what's on file as it stands, but it can close without running 


## permit（1 题）

| 任务 | 交付形态 | 标题 |
|---|---|---|
| `permission-to-operate-memo` | docx | — |

### 交付规格明细

#### `permission-to-operate-memo`
- docx `filesystem/Corwyn_PTO_Memo.docx`
  - 标题：H?:1. Answer / H?:2. What stands in the way: summary / H?:3. The items in detail / H?:3.1 Item 1: the RTU’s station supply is taken from the Facility side of the POI  / H?:3.2 Item 2: no way to energize the Facility before Permission to Operate, so the / H?:3.3 Item 3: the SOC confirmation on the commissioning checklist is not a TCS-02  / H?:4. What is in order, and what this memo does not cover / H?:5. Path to Permission to Operate / H?:6. For the SOC now / H?:Record relied on (as at 07/14/2025)
  - 疑似章节：ALLENIOM UTILITIES — DER PROGRAM OFFICE / INTERNAL MEMORANDUM / the site’s queue position (Meera Vellanki, weekly queue reports); and / Reviewed and approved for issue
  - 表格列头：[['Doc no.', 'DPO-PTO-0629-01'], ['TO:', 'Lena Kovalchuk, SOC Shift Supervisor, Sy'], ['#', 'What stands in the way', 'Rests on', 'Who has to act', 'Before 08/04/2025?'], ['Step', 'What', 'By'], ['Reviewing Engineer, P.E., DER Program Of', '']]
- 收尾摘要写法：The memo says Permission to Operate **cannot issue on 08/04/2025** and tells Lena to hold it. It is saved as `/filesystem/Corwyn_PTO_Memo.docx` (5 pages), and I opened one work pac
