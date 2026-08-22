# 05 — 数据集生命周期：版本、编辑、导出、无问题提示

> 覆盖 BRD：8.10 评测集版本与数据划分 / 8.12 评测集事后编辑 / 8.13 目录架构浏览与导出 / 8.14 增量更新 / 8.15 泛化 / 8.16 评测集回流 / 8.17 无问题提示 / 8.22 三类评测集来源统一管理（基础能力已实现，治理审核延期）
> Demo 状态：必做（基础版本冻结 + 导出）；其余延后

---

## 1. BRD 需求摘要

### 8.10 评测集版本与数据划分

| 需求编号 | 需求 |
|---|---|
| FR-DS-001 | 每条样本含 case_id/intent_id/question/type/scope/difficulty/gold_answer/must_have_points/acceptable_answers/evidence/eiu_ids/content_priority/review_status |
| FR-DS-002 | 评测集整体交付，不做 dev/val/test 拆分（评测看整个评测集效果）；一个版本即一份完整、可重复评测的评测集 |
| FR-DS-003 | 版本冻结：记录语料库版本/文档版本/解析器/OCR/嵌入模型/术语表/关系规则/生成模型/提示词/验证模型/审核 Skill 版本/覆盖率/创建时间/发布人 |

### 8.12 评测集事后编辑

| 需求编号 | 需求 |
|---|---|
| FR-DS-EDIT-001 | 手动编辑：问题文本/标准答案/答案要点/可接受答案/证据列表/题型/范围/难度/优先级/预期行为 |
| FR-DS-EDIT-002 | 删除（标记 retired 保留审计）：被删样本不参与统计与导出，但保留记录供审计；P0 删除需人工确认 |
| FR-DS-EDIT-003 | 版本草案：草案可直接编辑；冻结或发布版本必须新建草案后再编辑 |
| FR-DS-EDIT-004 | 编辑审计：操作人/时间/前后内容/原因/规则编号/新版本号 |

### 8.13 目录架构浏览与导出

| 需求编号 | 需求 |
|---|---|
| FR-DS-TREE-001 | 按原文档 section_path 树形浏览，标注每章节样本数/EIU覆盖率/未覆盖缺口 |
| FR-DS-TREE-002 | 两种导出组织方式：扁平导出（case列表）/ 目录结构导出（按文档→章节→小节嵌套） |
| FR-DS-TREE-003 | 导出附带各级节点覆盖率摘要 |

### 8.13.1 评测集表格视图与可视化（新增）

| 需求编号 | 需求 |
|---|---|
| FR-DS-GRID-001 | 评测集表格化浏览与编辑（Excel 式）：支持按任意列筛选、排序、聚合统计；原生（native）与泛化（augmentation）题目同表呈现并可按来源筛选 |
| FR-DS-VIZ-001 | 参数可视化：对难度/优先级/EIU类型/章节/scope 等维度生成分布统计图（柱状/饼图），随表格筛选实时联动 |

### 8.14 文档更新处理策略（覆盖式整体作废 + 全量重算，无增量更新）

> **决策：移除所有增量更新方案。** 文档重传只采用「覆盖式整体作废 + 全量重算」，
> 不对旧 EIU 做 superseded/conflicted/deprecated 等增量失效回写，也不对未变化 EIU
> 做题目复用。原因：增量回写依赖稳定的 EIU 跨版本映射，而语料整体覆盖后题目语义可能漂移，
> 复用旧题会引入不一致，整体作废重算更可控、可审计。

| 需求编号 | 需求 | 处置 |
|---|---|---|
| FR-DS-REBUILD-001 | 文档重传（content_hash 变化）触发覆盖式重算：删除该文档全部 block / 向量 / EIU / 题目（整体作废），再全量重新分段 + 向量化 + 抽 EIU + 全量生成题面 | 采用（见 §3.3） |
| FR-DS-REBUILD-002 | 重算进度可观测：phase = parsing → eiu_extract → rebuild，前端据 progress 渲染进度条，完成后提示「已更新完成」 | 采用（见 §3.3） |
| FR-DS-INC-001 / FR-DS-INC-002 | 增量 EIU 失效回写 / 增量补题 | **已废弃，不再实现** |

### 8.15 泛化（表述替换 / 扩写，输出模式 B）

| 需求编号 | 需求 |
|---|---|
| FR-DS-GEN-001 | 已发布集受控替换与旧变体淘汰：同 intent 替换（retired 旧变体）/ 规范问题本体替换（语义实质变化则新建 intent_id）/ 重校验 / 不重复计覆盖 |

### 8.16 评测集回流（不纳入本平台）

评测结果用于给待测智能体打分、归因与优化；智能体回答不佳不反向认定评测集有问题，因此本平台不提供评测后回流、回流工作台或基于 ErrorBook 的自动修题闭环。人工发现题目、答案或证据内容问题时，仅在 m08 运行前修订 m03 候选题，复检通过后再冻结为新版本；既有冻结版本和已开始的评测运行均不改写。

### 8.17 无问题提示（不发布空评测集）

| 需求编号 | 需求 |
|---|---|
| FR-DS-EMPTY-001 | 无问题判定：EIU 总数 = 0 或 全部不可出题（is_questionable=false）、无未处理文段 |
| FR-DS-EMPTY-002 | 无问题提示：直接告知用户"无问题可生成"并说明原因，不进入发布流程、不产出空版本；保留无问题判定审计结果 |
| FR-DS-EMPTY-003 | 后续：可追加文档 / 调整排除规则 → 重新触发解析→EIU→补题 → 产出含题新版本 |
| FR-DS-EMPTY-004 | 门禁衔接：EIU>0 时覆盖率门禁生效；EIU=0 时不阻断（直接提示，不生成空集） |

### 8.22 三类评测集来源统一管理（BRD V1.3，基础能力已实现）

| 需求编号 | 需求 | 当前状态 |
|---|---|---|
| FR-DS-SRC-001 | 直接上传评测集（单轮模板 `q/a/evidence/dimension`，`evidence` 不填标记"无证据样本"）→ 格式校验 → 质量评估 → 入库 | 已实现（`services/uploaded_set.py` + POST /api/eval-sets/upload） |
| FR-DS-SRC-002 | 多轮评测集模板（`session_id` + `turns[]`，`key_turn` 类型 `memory`/`coherence`，`depends_on_turns`，最终轮 `a` 必填） | 已实现字段校验；完整评分（memory/coherence）阶段 2 |
| FR-DS-SRC-003 | 评分口径（运行侧配置）：短答案规范化精确匹配；长答案语义相似度 + 固定校准集 | 已实现（`services/scoring.py`，m08 评测时使用） |
| FR-DS-SRC-004 | 公共评测集库：组织方预置、用户只查看与选择使用、不开放共享入库；条目经质量评估与治理审核、版本化；维度体系可配置、暂不写死 | 已实现（`services/public_set.py` + /api/public-sets、/api/dimensions） |
| FR-DS-SRC-005 | Agent 评测前评测集组合选择：指定单个评测集 / 勾选公共库维度 / 多来源合并成临时标准化评测集 | 已实现（`services/composition.py` + /api/compositions） |
| FR-DS-SRC-006 | 无证据样本降级标注，不参与证据回溯率统计 | 已实现（`no_evidence` 标记） |

> **覆盖率适用范围（决策 3）**：EIU 覆盖率、85% 门禁与 P0 全覆盖仅适用于**文档生成评测集**；上传评测集与公共评测集库不产生 EIU、不参与覆盖率计算，只做质量评估与组合选择。

> **治理审核说明（Demo 简化）**：上传评测集入库状态为 `quality_checked`（格式校验 + 质量评估通过）；
> S0 治理审核（内容安全 / 隐私 / 证据核验）与"低分提示确认后发布"随 m04 治理审核 Skill 一起在后续版本落地，
> Demo 阶段由前端在发布/组合前向用户提示质量评估结果确认；**未通过治理审核的文档生成、上传和公共库产物不得标记为正式 `published`**。

---

## 2. 版本管理技术方案

### 2.1 版本冻结流程

```
用户触发 freeze：
  1. 检查前置条件：EIU 覆盖率达到门禁（仅文档生成评测集适用）、所有 case 质量校验通过
  2. 生成 version_number（v1.0.0, v1.1.0, ...）
  3. 记录完整快照元信息（见下表）
  4. 状态置为 frozen
  5. 冻结后该版本不可修改；后续需变更的，走新版本草案（见 3.2）
```

> Demo 的 `frozen` 是内部不可变快照，不等同正式 `published`；正式发布必须在 m04 治理审核 Skill 落地后满足 `governance_passed`、用户确认及 S0 门禁。

### 2.2 版本快照信息（FR-DS-003）

**dataset_version 表：**

| 字段 | 类型 | 说明 |
|---|---|---|
| version_id | INT PK | |
| version_number | VARCHAR | v1.0.0 |
| status | VARCHAR | draft / frozen / published |
| case_count | INT | |
| coverage_report_id | INT FK | |
| split_config | JSON | 交付配置（导出格式、是否含 retired 等）；默认整集导出，无 dev/val/test 拆分 |
| snapshot_metadata | JSON | 见下方 |
| created_at | DATETIME | |
| frozen_at | DATETIME | |

**snapshot_metadata 内容：**

```json
{
  "corpus_version": "v3",
  "document_versions": {"doc_1": "v1", "doc_2": "v2"}  // 评测集版本记录其生成时所依据的文档标识；源文档覆盖更新后重新生成新评测集版本，旧文档不保留
  "parser_version": "pymupdf-1.24.0",
  "embedding_model": "BAAI/bge-small-zh-v1.5",
  "llm_model": "gpt-4o-mini-2024-07-18",
  "eiu_extraction_prompt_version": "eiu_v2",
  "question_prompt_version": "qg_v1",
  "answer_prompt_version": "ag_v1",
  "quality_check_prompt_version": "qc_v1",
  "coverage": {
    "weighted": 0.913,
    "p0": 1.0,
    "p1": 0.942,
    "p2": 0.827
  },
  "created_by": "张工",
  "created_at": "2026-07-24T10:00:00Z"
}
```

---

## 3. 编辑与生命周期（Demo 基础版 + 后续版本规划）

### 3.1 编辑策略（草案直接编辑；冻结/发布版本新建草案）

```
支持操作：
  - PUT /api/candidate-cases/{case_id} → 修改 m03 候选题的问题、答案、证据、题型、难度或优先级
  - POST /api/candidate-cases/{case_id}/quality-check → 显式调用 m04 单题复检
  - PUT /api/cases/{case_id} / DELETE /api/cases/{case_id} → 仅用于未冻结的 eval_case 草案；冻结/发布版本返回 409

编辑后行为（Demo 已实现的最小闭环）：
  1. 人工修订候选题，服务端仅记录变更字段和操作人审计，不把题干、答案或证据正文写入审计日志；状态强制回退 `candidate` 并清空旧失败标签。
  2. 调用单题复检；通过后状态为 `quality_verified`，hard 失败可能由 m04 重生为替代题，soft 失败保留待人工处理。
  3. 显式 `POST /api/freeze` 生成新的不可变 `eval_case` 快照。旧冻结集、其上的组合和 m08 运行输入不被修改。
  4. `doc_generated` 组合只接受 `frozen` 版本；因此 m08 只能消费已冻结快照，不能直接消费待修订候选题。
```

### 3.2 版本草案与编辑审计（FR-DS-EDIT-003/004）

- 默认：草案编辑直接保存（见 3.1），不产生新版本。
- 冻结或已发布版本：必须显式"另存为新版本草案"；一次编辑会话的多条增删改作为一个批次提交，原版本保留；可 revert 到上一草案版本，已发布版本不可撤销。
- 编辑审计：所有修改操作留痕（操作人/时间/前后内容/原因/规则编号）。

### 3.3 文档更新处理（FR-DS-INC，Demo 采用覆盖式全量重算）

文档重传触发覆盖式全量重算（更新触发见 01 §2.8 的 doc_update_job）：

```
新增文档后：
  1. 仅重解析/向量化新增文档
  2. EIU 抽取仅对新增 Block
  3. 检查新增 EIU 是否与已有 EIU 冲突/替代
  4. 仅对新增/变化 EIU 补题
  5. 未变化 EIU 的已审核题目直接复用 → 新版本

同文档更新后（content_hash 变化，FR-CORPUS-004，覆盖式）：
  1. 删除旧版本该文档的全部 block / 向量 / EIU / 题目（整体作废）
  2. 全量重新分段 + BGE 向量化 + 抽 EIU（doc_update_job.phase = parsing → eiu_extract，progress 按总 Block 数推进）
  3. 全量生成题面（不复用旧题，因语料已整体覆盖）
  4. 更新完成（phase = rebuild）→ job.status = done，message = "已更新完成"
  5. 前端据 job 进度渲染进度条，完成后提示"已更新完成"

> 说明：以上「新增文档增量补题」仅描述理想增量路径，已被决策废弃（见 §8.14）。
> 当前实现统一采用覆盖式：任何文档重传均整体作废该文档相关产物并全量重算，不再做
> 跨版本的 EIU/题目复用。
> 已冻结版本保持不可变；重传完成后由用户显式 `freeze` 创建包含新产物的新版本。

### 3.4 泛化（FR-DS-GEN，输出模式 B，必做）

```
用户对某规范问题触发"表述替换"：
  - 同 intent 替换：新表述仍绑原 intent_id，旧变体标记 retired
  - 规范问题本体替换：语义实质变化则新建 intent_id
  - 替换后重跑质量校验 + 治理审核
  - 不重复计覆盖率
```

### 3.5 评测集组合选择与三类来源统一管理（BRD V1.3 §8.22，已实现）

Agent 评测前（自动运行阶段）用户可选择：指定单个评测集、勾选公共评测集库维度、或合并多来源（文档生成 / 上传 / 公共库）形成**临时标准化评测集**；组合结果作为评测运行配置记录、版本化并参与审计。三类来源与组合选择均已实现（见 §8.22 表），组合解析结果直接作为 m08 EvaluationRun 的输入。

实现：`services/composition.py` 提供 `create_composition`（组合校验 + 审计）与 `resolve_composition`（组合解析为统一运行输入，供 m08 EvaluationRun 消费）；来源支持 `doc_generated`（冻结版本 eval_case）/ `uploaded`（上传评测集）/ `public`（公共库），公共库可按维度勾选过滤。

---

## 4. 目录架构浏览与导出

### 4.1 树形浏览 API（FR-DS-TREE-001）

> 说明：
> - 未开启跨文档时：生成结果按各文档原有章节树组织，目录即原文档 `section_path` 结构；用户选择多个文档时按文档分组并列、互不混合，并可选择"目录导出"。
> - （后续版本）开启跨文档且选择目录导出时：单文档题仍按各文档章节树分文件夹，"跨文档综合题"单独形成一个"跨文档"文件夹，不混入任何单文档章节树（Demo 阶段不生成跨文档题）。

```
GET /api/tree
  → 按原文档 section_path 构建树形结构
  → 每个节点标注样本数、EIU 覆盖率、未覆盖缺口
```

**响应格式：**

```json
{
  "corpus_id": 1,
  "tree": [
    {
      "document_name": "授信政策指引.pdf",
      "sections": [
        {
          "section_path": "第三章 授信准入",
          "eiu_count": 28,
          "case_count": 28,
          "coverage_pct": 100.0,
          "children": [
            {
              "section_path": "3.1 基本条件",
              "eiu_count": 12,
              "case_count": 12,
              "coverage_pct": 100.0
            }
          ]
        }
      ]
    }
  ]
}
```

### 4.2 导出格式

**扁平导出（JSONL）：**
```jsonl
{"case_id":"case_000001","question":"...","gold_answer":"...","evidence":[...]}
{"case_id":"case_000002","question":"...","gold_answer":"...","evidence":[...]}
```

**目录结构导出（JSON）：**
- 按"文档 → 章节 → 小节"嵌套；每个 section 含该章节下的 cases。
- **跨文档题隔离（后续版本）**：当用户开启跨文档、且版本含跨文档综合题时，单文档题仍按各文档章节树分文件夹；"跨文档综合题"单独归入顶层 `cross_document` 所形成的"跨文档"文件夹，不混入任何单文档章节树（Demo 阶段不生成跨文档题）。

```json
{
  "dataset_version": "v1.0.0",
  "coverage": {...},
  "documents": [
    {
      "document_name": "授信政策.pdf",
      "sections": [
        { "section_path": "3.1 基本条件", "cases": [...] }
      ]
    }
  ],
  "cross_document": [
    {
      "title": "跨文档综合题",
      "cases": [
        {
          "case_id": "case_x001",
          "question": "...",
          "gold_answer": "...",
          "scope": "cross_document",
          "evidence": [
            {"document_name": "授信政策.pdf", "block_id": 123},
            {"document_name": "财报.xlsx", "block_id": 456}
          ]
        }
      ]
    }
  ]
}
```
（仅当版本含跨文档题且选择目录导出时存在 `cross_document` 字段；未开启跨文档时不输出该字段。）

**Excel 导出：** 扁平表格 + 按章节筛选列。

### 4.3 无问题提示（不发布空评测集，FR-DS-EMPTY）

当无可出题内容时，平台直接明确告知用户"无问题可生成"，**不进入发布流程、不产出空评测集，但保留无问题判定审计结果**：

```
判定条件：
  - EIU 总数 = 0（全部被排除或确无实质内容）
  - 或所有 EIU 均标记为不可出题（is_questionable = false）
  - 无"未处理"或"抽取失败且无排除记录"的文段

行为：
  - 前端直接提示"无问题可生成"，并给出原因（无 EIU / 全部排除 / 全部不可出题）
  - 不创建 dataset_version、不写入空集、不触发覆盖率门禁；保存判定时间、原因、文档范围和 EIU 统计的审计结果
  - 用户可追加文档或调整排除规则后重新生成

注：原"发布空评测集（样本数=0）"不再采用——空结果以提示呈现，而非生成一个空版本。

### 4.4 评测集表格视图（Excel 式，FR-DS-GRID-001）

评测集在页面上以类 Excel 数据网格呈现，原生题目与泛化题目同表展示，便于批量审阅与编辑：

- **列即字段**：case_id / source(native\|augmentation) / question / gold_answer / type / scope / difficulty / content_priority / intent_id / eiu_ids / evidence / review_status。
- **来源区分**：`source` 列标记原生或泛化，可下拉筛选只看某一类（原生或泛化）。
- **筛选**：按任意列条件筛选（文本包含、枚举多选、难度/优先级范围等），多列条件 AND 组合。
- **排序**：点击列头升/降序，支持多列排序。
- **统计**：状态栏/侧栏显示当前筛选结果计数，并按难度/优先级/类型/EIU 等维度聚合（如各难度题量、P0 题量），随筛选实时更新。
- **就地编辑**：候选题审阅页编辑 question/answer/evidence/优先级等，提交调用 `PUT /api/candidate-cases/{case_id}`，再显式调用单题复检；版本表格中的冻结快照只读，不通过该入口改写。
- **分页**：大数据量分页加载；统计基于全量筛选结果而非当前页。

### 4.5 参数可视化统计图（FR-DS-VIZ-001）

对评测集关键参数生成分布统计图，辅助质量研判：

- **维度**：难度（L1/L2/L3）、优先级（P0/P1/P2）、EIU 类型、章节（section_path）、scope（单文档/跨文档）、来源（native/augmentation）。
- **图表**：柱状图（各维度计数）、饼图（占比），可切换维度；难度等参数默认展示分布直方图。
- **联动**：统计图与 4.4 表格视图共享同一筛选条件——筛选后统计图同步刷新，仅反映当前子集分布。
- **数据来源**：统计基于 `GET /api/versions/{version_id}/stats`（已按筛选聚合），不依赖前端逐条计算全量。

---

## 5. API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/freeze` | 冻结版本 |
| GET | `/api/versions` | 版本列表 |
| GET | `/api/versions/{version_id}` | 版本详情（含快照元信息） |
| GET | `/api/versions/{version_id}/export?format=jsonl` | 导出评测集 |
| GET | `/api/versions/{version_id}/export?format=json` | 目录结构导出 |
| GET | `/api/versions/{version_id}/export?format=xlsx` | 当前返回 501（Excel 导出待实现） |
| GET | `/api/tree` | 目录树浏览 |
| GET | `/api/versions/{version_id}/cases` | 表格视图数据（支持 filter/sort/page/source） |
| GET | `/api/versions/{version_id}/stats` | 当前筛选下的聚合统计与分布（供可视化） |
| PUT | `/api/candidate-cases/{case_id}` | 冻结前人工修订 m03 候选题，自动回退 `candidate` 并记录字段级审计 |
| POST | `/api/candidate-cases/{case_id}/quality-check` | 对修订候选题执行 m04 单题复检；通过后才能被冻结 |
| PUT | `/api/cases/{case_id}` | 未冻结 eval_case 草案的编辑；冻结/发布快照只读 |
| DELETE | `/api/cases/{case_id}` | 删除样本（标记 retired，保留审计） |
| POST | `/api/eval-sets/upload` | 上传评测集（单轮/多轮）：格式校验 + 质量评估 + 入库 |
| GET | `/api/eval-sets/uploaded` | 上传评测集列表 |
| GET | `/api/eval-sets/uploaded/{set_id}` | 上传评测集详情（含样本） |
| DELETE | `/api/eval-sets/uploaded/{set_id}` | 删除上传评测集（含样本） |
| POST | `/api/public-sets` | 公共评测集库预置导入（组织方） |
| GET | `/api/public-sets` / `/api/public-sets/{set_id}` | 公共库列表 / 详情 |
| PUT/DELETE | `/api/public-sets/{set_id}` | 公共库更新 / 停用（版本化留痕） |
| GET | `/api/dimensions` | 评测维度体系（可配置） |
| POST | `/api/compositions` | 创建评测集组合（指定单个 / 勾选维度 / 多来源合并） |
| GET | `/api/compositions` / `/api/compositions/{composition_id}` | 组合列表 / 详情（含解析样本） |
| DELETE | `/api/compositions/{composition_id}` | 删除组合 |

---

## 6. Demo 实现清单

- [x] `dataset_version` 表 + 版本冻结 API（含快照元信息记录）：冻结时把 m03 生成 + m04 通过门禁的 generated_case 快照为不可变 eval_case 副本
- [x] JSONL 扁平导出（整集，不做 dev/val/test 拆分）
- [x] JSON 目录结构导出（按文档 → 章节 → 小节嵌套；跨文档题隔离字段预留，Demo 阶段不生成跨文档题故不输出 `cross_document`）
- [x] 无问题判定 + 提示逻辑（不发布空集）：基于 m02 EIU 总数 / 是否全不可出题 / 是否存在通过门禁样本三重判定
- [ ] 无问题判定审计结果持久化（不发布空集，但保留原因、范围和 EIU 统计）
- [x] 冻结前人工修订最小闭环：候选题修订 → 字段级审计 → m04 单题复检 → 显式冻结新版本；m08 仅消费 frozen 文档版本
- [x] 评测集表格数据与候选题修订接口：冻结版本表格只读；候选题通过专用修订/复检接口处理（前端网格待补）
- [x] 参数可视化统计图：GET /api/versions/{version_id}/stats 已按维度聚合，前端图表待补
- [x] 上传评测集（单轮/多轮模板校验 + 最终轮质量评估 + 原子入库，`uploaded_set.py`）
- [x] 公共评测集库（预置导入 + 维度体系 + 版本化停用；状态为 `quality_checked`，不伪造治理通过，`public_set.py`）
- [x] 评测集组合选择（校验 + 审计 + 解析为统一运行输入，`composition.py`）
- [x] 评分口径（短答案规范化精确匹配 / 长答案语义相似度，`scoring.py`）
- [ ] 完整的冻结/发布版本“另存为草案”、编辑批次、前后内容/原因审计与覆盖率重算编排（FR-DS-EDIT-003/004）
- [x] 文档重传采用覆盖式整体作废 + 全量重算（见 §3.3 与 §8.14）；增量更新（FR-DS-INC）已废弃，不再实现
- [ ] 泛化（输出模式 B，基于种子问答对扩写更多相关问题对）
- [x] 明确不做评测后数据回流：ErrorBook 仅用于 m08 智能体评测诊断，不驱动评测集修订
- [ ] （延后）真实 Excel 导出（当前 `export?format=xlsx` 明确返回 501，待引入 XLSX 生成依赖）

### 6.1 与 m01–m04 的数据衔接（实现要点）

| 模块 | 数据表 / 接口 | m05 用途 |
|---|---|---|
| m02 EIU 覆盖 | `eiu`（list_eius）、`coverage_report`（save_coverage_report） | 无问题判定（EIU 总数 / is_questionable）、树形覆盖率分母；冻结时落库 coverage_report 并回填 `coverage_report_id`（FR-DS-003 外键） |
| m03 生成 | `generated_case`（list_generated_cases） | 冻结时筛选 `review_status ∈ {quality_verified, governance_passed, user_confirmed, published}` 的样例，快照为 eval_case |
| m04 质量治理 | `generated_case.review_status` 状态机 | Demo 冻结仅纳入通过质量校验的样本；正式发布还必须通过治理审核，编辑后回退 candidate |
| m01 数据基座 | `document_block`、`doc_update_job` | 文档重传触发 `rebuild_on_reupload` 覆盖式重算；树形反查 section_path / document_name |

> 冻结集为 **不可变快照**：冻结后 eval_case 不再随 m03/m04 后续变更而变；如需更新，走新版本（freeze 生成新 version_number）。
