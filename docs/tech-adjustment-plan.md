# EvalForge 架构调整方案（BRD V1.3：评测集生成 + 评测集管理 + Agent 评测）

> 状态：关键决策已确认（m08 独立、上传样本独立落表、Agent 评测 Demo 必做、适配器 A+B、模板沿用 q/a/evidence/dimension），
> m05 三类来源与 m08 自动评测已落地；本文件作为实施依据存档 | 依据：`evaluation_dataset_platform_brd.md` V1.3（§3.1/§8.22/§9/§11/§15）
> 范围：后端模块划分、数据表、接口清单、Demo 落点；不推翻现有 m01–m07，做增量扩展。

---

## 1. 目标与范围

平台定位已升级为"评测数据资产管理 + 自动构建 + Agent 能力评估"（BRD §3.1），三大块：

| 板块 | BRD 章节 | 现状 | 本方案动作 |
|---|---|---|---|
| 评测集生成 | §8.1–§8.9 | m01–m04 已实现 | 不动主线，仅微调 |
| 评测集管理 | §8.10–§8.17、§8.22 | m05 有版本/编辑/导出；三类来源预留 | 扩展 m05（上传评测集、公共库、组合选择） |
| Agent 评测 | §9 | 无模块；m06 边界过时 | 新增 m08（自动运行 + 指标 + 归因 + 优化），m06 边界更新 |

附带补齐：§8.20 业务需求书→测试功能点（无代码，见 §6 落点）。

---

## 2. 模块划分

### 2.1 m05_dataset_lifecycle 扩展（评测集管理，三类来源）

新增服务（沿用现有 `services/` 结构）：

| 服务 | 职责 | 对应 BRD |
|---|---|---|
| `services/uploaded_set.py` | 上传评测集：单轮模板（JSON/JSONL 先支持，Excel/CSV 预留可插拔）、格式校验、质量评估、入库状态机；多轮字段保留不启用 | FR-DS-SRC-001/002/003/006 |
| `services/public_set.py` | 公共评测集库：组织方预置、维度可配置、版本化（新增/更新/停用留痕） | FR-DS-SRC-004 |
| `services/composition.py` | 评测集组合选择：指定单个/勾选维度/多来源合并 → 临时标准化评测集（EvalSetComposition） | FR-DS-SRC-005 |
| `services/scoring.py` | 评分口径（运行侧配置）：短答案规范化精确匹配、长答案语义相似度 + 固定校准集 | FR-DS-SRC-003 |

### 2.2 新增 m08_auto_evaluation（Agent 评测与后评估）

```
modules/m08_auto_evaluation/
├── api.py                  # /api/evaluation-runs、/api/adapters、/api/error-book
├── schemas.py
├── services/
│   ├── adapter.py          # 待测系统标准适配器（FR-RUN-001）：mock + OpenAI 兼容双实现（决策 4），注册表预留真实系统扩展
│   ├── runner.py           # 批量运行（异步任务，进度复用 doc_update_job 模式）
│   ├── metrics.py          # 分层指标：检索 / 答案 / 拒答 / 忠实性 / 耗时成本（FR-METRIC-001~004）
│   ├── diagnosis.py        # D1–D9 一级归因 + 归因顺序（FR-DIAG-001/002）
│   └── optimization.py     # 优化建议 + ErrorBook + 回归比较（FR-OPT-001~003）
└── README.md
```

### 2.3 m06 边界调整（回流闭环）

- m06 保留"评测后数据回流"：回流工作台、人工标注、修题闭环（FR-DS-FB）；
- 数据来源从"仅外部回传"扩展为 **m08 运行结果（ErrorBook）+ 人工标注**；
- 更新 m06 README 顶部边界声明：不再写"自动评测不在本平台范围"。

### 2.4 shared 层

- `modules/shared/services/adapter_registry.py`：适配器注册表（名称 → 类），运行配置按 id 引用；
- `doc_update_job` 复用：新增 job_type（`evaluation_run` / `set_upload`），不新建任务表；
- 审计：组合创建、运行触发、公共库维护走 `audit_log`（已有）。

---

## 3. 数据表设计（database.py 新增，create_all 自动建表）

| 表 | 关键字段 | 说明 |
|---|---|---|
| `uploaded_eval_set` | set_id、name、template_type(single/multi)、source_file、dimension、review_status、quality_snapshot(JSON)、created_at | 上传评测集主记录 |
| `uploaded_eval_case` | case_id、set_id(FK)、q、a、evidence、dimension、session_id、turns(JSON)、key_turn、depends_on_turns(JSON)、no_evidence、quality(JSON) | 上传样本（单轮/多轮字段合一；多轮字段保留，Demo 不启用） |
| `public_eval_set` | set_id、name、version、dimensions(JSON)、review_status、quality_snapshot(JSON)、status(active/retired) | 公共评测集库条目（版本化） |
| `eval_set_dimension` | dimension_id、code、name、description、enabled | 可配置维度体系（FR-DS-SRC-004） |
| `eval_set_composition` | composition_id、name、items(JSON: [{source, set_id/version_id, dimension}])、created_at | Agent 评测前组合（FR-DS-SRC-005） |
| `evaluation_run` | run_id、composition_id(FK)、adapter_config(JSON)、status、progress、total/finished、started_at/finished_at、model_version | 一次批量运行 |
| `evaluation_case_result` | result_id、run_id(FK)、case_uid、question、gold_answer、answer、retrieved(JSON)、scores(JSON)、diagnosis、status | 单题输出 + 分层评分 + 归因 |
| `error_book_item` | item_id、run_id(FK)、case_uid、diagnosis(D1–D9)、root_cause、optimization、regression(JSON)、status | ErrorBook（FR-OPT-003） |

关系：`eval_set_composition → evaluation_run → evaluation_case_result → error_book_item`；
上传/公共库样本不参与 EIU 覆盖率（BRD 决策 3），运行输入为"组合后的临时标准化评测集快照"。

---

## 4. 接口清单（新增）

### 4.1 m05（三类来源）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/eval-sets/upload` | 上传评测集（单轮/多轮），格式校验 + 质量评估 + 入库（异步） |
| GET | `/api/eval-sets/uploaded` | 上传评测集列表 |
| GET | `/api/eval-sets/uploaded/{id}` | 上传评测集详情（含样本） |
| POST | `/api/public-sets` | 公共库条目导入（组织方预置） |
| GET | `/api/public-sets` / `/api/public-sets/{id}` | 公共库列表 / 详情 |
| PUT/DELETE | `/api/public-sets/{id}` | 公共库条目更新 / 停用（版本化留痕） |
| GET | `/api/dimensions` | 维度体系（可配置） |
| POST | `/api/compositions` | 创建评测集组合（指定单个/勾选维度/多来源合并） |
| GET/DELETE | `/api/compositions/{id}` | 组合详情 / 删除 |

### 4.2 m08（Agent 评测）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/evaluation-runs` | 发起运行（composition_id + adapter 配置）→ 202 + run_id |
| GET | `/api/evaluation-runs` | 运行列表 |
| GET | `/api/evaluation-runs/{id}` | 运行进度 / 状态 |
| GET | `/api/evaluation-runs/{id}/results` | 分层指标汇总（按指标/难度/文档分组） |
| GET | `/api/evaluation-runs/{id}/failures` | D1–D9 失败归因列表 |
| POST | `/api/evaluation-runs/{id}/retry` | 重跑（开发集回归） |
| GET | `/api/error-book` | ErrorBook 查询（回流工作台数据源，供 m06） |
| POST | `/api/adapters` | 待测系统适配器配置（CRUD） |

---

## 5. 核心数据流

```
文档生成评测集（m01–m04 已有）
上传评测集（m05 新增）──┐
公共评测集库（m05 新增）─┼─→ EvalSetComposition（组合/维度勾选）
                        │        │
                        └────────┘
                                 ▼
                        EvaluationRun（m08，异步批量）
                                 ▼
                  分层指标 + D1–D9 归因（m08）
                                 ▼
                ErrorBook（优化建议/回归）─→ m06 回流工作台（修题闭环 → 新版本）
```

---

## 6. Demo 落点（对应 BRD §15 阶段 1）

**Demo 必做：**

- 上传评测集：单轮模板（`q/a/evidence/dimension`）+ 格式校验 + 质量评估（数据完整率/重复问题比例/有效 QA 比例/覆盖维度）+ 入库（文件格式：JSON/JSONL 先支持，Excel/CSV 预留可插拔）；
- 公共评测集库：占位条目演示（组织方预置、用户只读选择），维度体系可配置、待首批数据固化；
- 评测集组合选择：指定单个 / 勾选公共库维度 / 多来源合并；
- Agent 评测：mock + OpenAI 兼容双适配器（决策 4），批量运行 + 基础指标（检索/答案/拒答/耗时）+ D1–D9 基础归因；
- 业务需求书→测试功能点（§8.20）：轻量 EIU 提取，不生成标准答案。

**延后（阶段 2+）：**

- 多轮评测集（memory/coherence）完整评分（决策 5：Demo 不开发，但前端/后端均保留功能点与字段占位，后续优化实现）；语义评分固定校准集（待 §18 确认）；
- 治理审核 Skill 全量 S0 规则；公共库维度体系固化；回流工作台 UI 深度集成。

---

## 7. 实施顺序（建议）

1. **数据层**：新增 8 张表 + audit 关联（create_all 自动迁移）；
2. **m05 三类来源**：上传评测集 → 公共库 → 组合选择（含质量评估与评分口径）；
3. **m08 自动评测**：适配器 → runner → 指标 → 归因 → ErrorBook；
4. **m06 边界与回流衔接**：ErrorBook → 回流工作台 → 修题 → 新版本；
5. **文档同步**：m05/m06/m08 README、modules/README、根 README、technical_design_demo、production-readiness-todo。

---

## 8. 决策确认（2026-08-18）

| # | 决策项 | 结论 |
|---|---|---|
| 1 | m08 模块归属 | **独立新增 m08_auto_evaluation**；m06 仅保留回流闭环 |
| 2 | 上传样本落表 | **独立 `uploaded_eval_case` 表**（不复用 generated_case） |
| 3 | Agent 评测 Demo 落点 | **Demo 必做**（运行 + 基础指标 + D1–D9 归因） |
| 4 | 待测系统形态 | **mock + OpenAI 兼容双适配器（A+B）**；真实系统经适配器注册表后续扩展 |
| 5 | 格式与多轮 | 文件格式**先支持 JSON/JSONL**，Excel/CSV 预留可插拔；**多轮 Demo 不开发，前端/后端保留功能点与字段占位**（作为后续优化项，见 §6）；**公共评测集库占位演示**（维度可配置，首批数据待确认） |
