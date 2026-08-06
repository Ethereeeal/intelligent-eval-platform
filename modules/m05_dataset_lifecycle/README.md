# 05 — 数据集生命周期：版本、编辑、导出、回流、无问题提示

> 覆盖 BRD：8.10 评测集版本与数据划分 / 8.12 评测集事后编辑 / 8.13 目录架构浏览与导出 / 8.14 增量更新 / 8.15 泛化 / 8.16 评测集回流 / 8.17 无问题提示
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
| FR-DS-EDIT-003 | 版本草案（可选）：用户显式"另存为新版本草案"时，一次编辑会话作为批次提交，生成新草案版本 |
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

### 8.16 评测集回流

| 需求编号 | 需求 |
|---|---|
| FR-DS-FB-001 | 人工回流标注：对已通过的问答对打"可疑/打回"标记 |
| FR-DS-FB-002 | 回流工作台视图：按标注类型/优先级/置信度/来源等维度过滤排序 |
| FR-DS-FB-003 | 回流筛选与分流规则：打回 / 可疑条目进入修题队列，由人工或规则决定修订方式（改题 / 改答案 / 改证据 / 停用） |
| FR-DS-FB-004 | 回流处理闭环：回流→标注→分流→处置（编辑走 FR-DS-EDIT）→重校验→新版本→关闭（详见 06，平台不重新评测） |

### 8.17 无问题提示（不发布空评测集）

| 需求编号 | 需求 |
|---|---|
| FR-DS-EMPTY-001 | 无问题判定：EIU 总数 = 0 或 全部不可出题（is_questionable=false）、无未处理文段 |
| FR-DS-EMPTY-002 | 无问题提示：直接告知用户"无问题可生成"并说明原因，不进入发布流程、不产出空版本 |
| FR-DS-EMPTY-003 | 后续：可追加文档 / 调整排除规则 → 重新触发解析→EIU→补题 → 产出含题新版本 |
| FR-DS-EMPTY-004 | 门禁衔接：EIU>0 时覆盖率门禁生效；EIU=0 时不阻断（直接提示，不生成空集） |

---

## 2. 版本管理技术方案

### 2.1 版本冻结流程

```
用户触发 freeze：
  1. 检查前置条件：EIU 覆盖率达到门禁、所有 case 质量校验通过
  2. 生成 version_number（v1.0.0, v1.1.0, ...）
  3. 记录完整快照元信息（见下表）
  4. 状态置为 frozen
  5. 冻结后该版本不可修改；后续需变更的，走新版本草案（见 3.2）
```

### 2.2 版本快照信息（FR-DS-003）

**dataset_version 表：**

| 字段 | 类型 | 说明 |
|---|---|---|
| version_id | INT PK | |
| corpus_id | INT FK | |
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

### 3.1 Demo 阶段编辑（直接保存，不强制新版本）

```
支持操作：
  - PUT /api/cases/{case_id} → 修改题目/答案/证据/优先级
  - DELETE /api/cases/{case_id} → 标记 retired（保留审计，不参与统计与导出）

编辑后行为（直接保存，不强制新版本）：
  - 修改直接落到当前版本 / draft，无需每次生成新版本
  - case.review_status 回退到 candidate
  - 自动触发重新质量校验
  - 覆盖率重新计算
  - 版本冻结（freeze）为独立的显式操作，编辑不自动触发；冻结后的版本不可直接编辑，需走新版本草案（见 3.2）
```

### 3.2 版本草案与编辑审计（FR-DS-EDIT-003/004，可选）

- 默认：编辑直接保存（见 3.1），不产生新版本。
- 版本草案（可选）：当用户显式"另存为新版本草案"时，一次编辑会话的多条增删改作为一个批次提交，生成新草案版本，原版本保留；可 revert 到上一草案版本，已发布版本不可撤销。
- 编辑审计：所有修改操作留痕（操作人/时间/前后内容/原因/规则编号）。

### 3.3 文档更新处理（FR-DS-INC，Demo 采用覆盖式全量重算）

文档重传触发覆盖式全量重算（更新触发见 01 §2.7 的 doc_update_job）：

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

### 3.4 泛化（FR-DS-GEN，输出模式 B，必做）

```
用户对某规范问题触发"表述替换"：
  - 同 intent 替换：新表述仍绑原 intent_id，旧变体标记 retired
  - 规范问题本体替换：语义实质变化则新建 intent_id
  - 替换后重跑质量校验 + 治理审核
  - 不重复计覆盖率
```

### 3.5 评测集回流（FR-DS-FB，Demo 不做，后续版本，详见 06）

```
闭环步骤：
  回流（外部评测回传 / 人工标注）
  → 分流（打回 / 可疑 → 修题队列）
  → 处置（编辑走 FR-DS-EDIT：改题 / 改答案 / 改证据 / 停用）
  → 重校验（质量校验）
  → 新版本（版本控制，见 §2）
  → 关闭（修订留痕）

注：平台不重新评测、不做失败归因，重评由外部评测系统负责；详见 06。
```

---

## 4. 目录架构浏览与导出

### 4.1 树形浏览 API（FR-DS-TREE-001）

> 说明：
> - 未开启跨文档时：生成结果按各文档原有章节树组织，目录即原文档 `section_path` 结构；用户选择多个文档时按文档分组并列、互不混合，并可选择"目录导出"。
> - （后续版本）开启跨文档且选择目录导出时：单文档题仍按各文档章节树分文件夹，"跨文档综合题"单独形成一个"跨文档"文件夹，不混入任何单文档章节树（Demo 阶段不生成跨文档题）。

```
GET /api/corpus/{corpus_id}/tree
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

当无可出题内容时，平台直接明确告知用户"无问题可生成"，**不进入发布流程、不产出空评测集**：

```
判定条件：
  - EIU 总数 = 0（全部被排除或确无实质内容）
  - 或所有 EIU 均标记为不可出题（is_questionable = false）
  - 无"未处理"或"抽取失败且无排除记录"的文段

行为：
  - 前端直接提示"无问题可生成"，并给出原因（无 EIU / 全部排除 / 全部不可出题）
  - 不创建 dataset_version、不写入空集、不触发覆盖率门禁
  - 用户可追加文档或调整排除规则后重新生成

注：原"发布空评测集（样本数=0）"不再采用——空结果以提示呈现，而非生成一个空版本。

### 4.4 评测集表格视图（Excel 式，FR-DS-GRID-001）

评测集在页面上以类 Excel 数据网格呈现，原生题目与泛化题目同表展示，便于批量审阅与编辑：

- **列即字段**：case_id / source(native\|augmentation) / question / gold_answer / type / scope / difficulty / content_priority / intent_id / eiu_ids / evidence / review_status。
- **来源区分**：`source` 列标记原生或泛化，可下拉筛选只看某一类（原生或泛化）。
- **筛选**：按任意列条件筛选（文本包含、枚举多选、难度/优先级范围等），多列条件 AND 组合。
- **排序**：点击列头升/降序，支持多列排序。
- **统计**：状态栏/侧栏显示当前筛选结果计数，并按难度/优先级/类型/EIU 等维度聚合（如各难度题量、P0 题量），随筛选实时更新。
- **就地编辑**：双击单元格编辑 question/answer/evidence/优先级等，提交调用 `PUT /api/cases/{case_id}`，触发重新质量校验、`review_status` 回退 candidate（复用 FR-DS-EDIT-001）。
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
| POST | `/api/corpus/{corpus_id}/freeze` | 冻结版本 |
| GET | `/api/corpus/{corpus_id}/versions` | 版本列表 |
| GET | `/api/versions/{version_id}` | 版本详情（含快照元信息） |
| GET | `/api/versions/{version_id}/export?format=jsonl` | 导出评测集 |
| GET | `/api/versions/{version_id}/export?format=json` | 目录结构导出 |
| GET | `/api/versions/{version_id}/export?format=xlsx` | Excel 导出 |
| GET | `/api/corpus/{corpus_id}/tree` | 目录树浏览 |
| GET | `/api/versions/{version_id}/cases` | 表格视图数据（支持 filter/sort/page/source） |
| GET | `/api/versions/{version_id}/stats` | 当前筛选下的聚合统计与分布（供可视化） |
| PUT | `/api/cases/{case_id}` | 手动编辑样本（表格视图就地编辑复用） |
| DELETE | `/api/cases/{case_id}` | 删除样本（标记 retired，保留审计） |

---

## 6. Demo 实现清单

- [x] `dataset_version` 表 + 版本冻结 API（含快照元信息记录）：冻结时把 m03 生成 + m04 通过门禁的 generated_case 快照为不可变 eval_case 副本
- [x] JSONL 扁平导出（整集，不做 dev/val/test 拆分）
- [x] JSON 目录结构导出（按文档 → 章节 → 小节嵌套；跨文档题隔离字段预留，Demo 阶段不生成跨文档题故不输出 `cross_document`）
- [x] 无问题判定 + 提示逻辑（不发布空集）：基于 m02 EIU 总数 / 是否全不可出题 / 是否存在通过门禁样本三重判定
- [x] 基础手动编辑 API（PUT /api/cases/{case_id}）+ 删除（DELETE 标记 retired）
- [x] 评测集表格视图：筛选/排序/聚合统计/就地编辑（GET cases + PUT cases 复用；前端网格待补）
- [x] 参数可视化统计图：GET /api/versions/{version_id}/stats 已按维度聚合，前端图表待补
- [ ] （可选）编辑批次与版本草案（FR-DS-EDIT-003/004）
- [x] 文档重传采用覆盖式整体作废 + 全量重算（见 §3.3 与 §8.14）；增量更新（FR-DS-INC）已废弃，不再实现
- [ ] 泛化（输出模式 B，基于种子问答对扩写更多相关问题对）
- [ ] （Demo 不做）评测后数据回流（06）
- [ ] （延后）Excel 导出（当前 export?format=xlsx 返回 CSV 字节占位，待 openpyxl 接入）

### 6.1 与 m01–m04 的数据衔接（实现要点）

| 模块 | 数据表 / 接口 | m05 用途 |
|---|---|---|
| m02 EIU 覆盖 | `eiu`（list_eius）、`coverage_report`（save_coverage_report） | 无问题判定（EIU 总数 / is_questionable）、树形覆盖率分母；冻结时落库 coverage_report 并回填 `coverage_report_id`（FR-DS-003 外键） |
| m03 生成 | `generated_case`（list_generated_cases） | 冻结时筛选 `review_status ∈ {quality_verified, governance_passed, user_confirmed, published}` 的样例，快照为 eval_case |
| m04 质量治理 | `generated_case.review_status` 状态机 | 门禁：仅通过质量校验 + 治理审核的样本纳入冻结集；编辑后回退 candidate |
| m01 数据基座 | `document_block`、`doc_update_job` | 文档重传触发 `rebuild_on_reupload` 覆盖式重算；树形反查 section_path / document_name |

> 冻结集为 **不可变快照**：冻结后 eval_case 不再随 m03/m04 后续变更而变；如需更新，走新版本（freeze 生成新 version_number）。
