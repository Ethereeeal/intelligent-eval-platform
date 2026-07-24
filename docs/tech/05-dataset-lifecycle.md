# 05 — 数据集生命周期：版本、编辑、增量、导出、回流、空评测集

> 覆盖 BRD：8.10 评测集版本与数据划分 / 8.12 评测集事后编辑 / 8.13 目录架构浏览与导出 / 8.14 增量更新 / 8.15 表述替换泛化 / 8.16 评测集回流 / 8.17 空评测集处理
> Demo 状态：必做（基础版本冻结 + 导出）；其余延后

---

## 1. BRD 需求摘要

### 8.10 评测集版本与数据划分

| 需求编号 | 需求 |
|---|---|
| FR-DS-001 | 每条样本含 case_id/intent_id/question/type/scope/difficulty/gold_answer/must_have_points/acceptable_answers/evidence/eiu_ids/content_priority/review_status |
| FR-DS-002 | 按 intent_id 或 EIU 簇拆分：开发集/验证集/锁定测试集/可选挑战集；同 intent 的所有改写必须在同一集合 |
| FR-DS-003 | 版本冻结：记录语料库版本/文档版本/解析器/OCR/嵌入模型/术语表/关系规则/生成模型/提示词/验证模型/审核 Skill 版本/覆盖率/创建时间/发布人 |

### 8.12 评测集事后编辑

| 需求编号 | 需求 |
|---|---|
| FR-DS-EDIT-001 | 手动编辑：问题文本/标准答案/答案要点/可接受答案/证据列表/题型/范围/难度/优先级/预期行为 |
| FR-DS-EDIT-002 | 删除与停用：delete（retired 保留审计）/ retire（不参与统计但保留），P0 删除需人工确认 |
| FR-DS-EDIT-003 | 编辑批次与版本：一次编辑会话生成新版本草案，记录前后差异，可撤销 |
| FR-DS-EDIT-004 | 编辑审计：操作人/时间/前后内容/原因/规则编号/新版本号 |

### 8.13 目录架构浏览与导出

| 需求编号 | 需求 |
|---|---|
| FR-DS-TREE-001 | 按原文档 section_path 树形浏览，标注每章节样本数/EIU覆盖率/未覆盖缺口 |
| FR-DS-TREE-002 | 两种导出组织方式：扁平导出（case列表）/ 目录结构导出（按文档→章节→小节嵌套） |
| FR-DS-TREE-003 | 导出附带各级节点覆盖率摘要 |
| FR-DS-TREE-004 | 跨文档目录聚合视图（可选） |

### 8.14 增量更新与问题生成

| 需求编号 | 需求 |
|---|---|
| FR-DS-INC-001 | 增量 EIU 失效/替代回写：新增文档使旧 EIU 被替代/冲突/失效时，标记 superseded/conflicted/deprecated |
| FR-DS-INC-002 | 增量问题生成：仅对新增/变化 EIU 补题，未变化 EIU 已审核题目直接复用 |

### 8.15 表述替换泛化

| 需求编号 | 需求 |
|---|---|
| FR-DS-GEN-001 | 已发布集受控替换与旧变体淘汰：同 intent 替换（retired 旧变体）/ 规范问题本体替换（语义实质变化则新建 intent_id）/ 重校验 / 不重复计覆盖 / 划分一致性 |

### 8.16 评测集回流

| 需求编号 | 需求 |
|---|---|
| FR-DS-FB-001 | 人工回流标注：对已通过的问答对打"可疑/打回"标记 |
| FR-DS-FB-002 | 回流工作台视图：按归因/优先级/置信度/来源等维度过滤排序 |
| FR-DS-FB-003 | 回流筛选与分流规则：D5→修题队列，D1-D4→系统优化队列 |
| FR-DS-FB-004 | 回流处理闭环：回流→归因→分流→处置→重校验→重新评测→新版本→回归→关闭 |

### 8.17 空评测集处理

| 需求编号 | 需求 |
|---|---|
| FR-DS-EMPTY-001 | 空评测集判定：EIU总数=0、实质文段对账率=100%、无未处理文段 |
| FR-DS-EMPTY-002 | 空评测集发布：样本数=0，版本记录完整，覆盖标记为N/A |
| FR-DS-EMPTY-003 | 空评测集后续：可追加文档→重新触发→产出含题新版本 |
| FR-DS-EMPTY-004 | 门禁衔接：EIU>0时覆盖率门禁生效；EIU=0时覆盖率不适用，不阻断 |

---

## 2. 版本管理技术方案

### 2.1 版本冻结流程

```
用户触发 freeze：
  1. 检查前置条件：EIU 覆盖率达到门禁、所有 case 质量校验通过
  2. 生成 version_number（v1.0.0, v1.1.0, ...）
  3. 按 intent_id 拆分为 dev/val/test 集合
  4. 记录完整快照元信息（见下表）
  5. 状态置为 frozen
  6. 冻结后该版本不可修改，后续编辑生成新版本草案
```

### 2.2 数据划分（FR-DS-002）

```
拆分策略：按 intent_id 哈希分组
  - 开发集 60%：用于错误分析和优化
  - 验证集 20%：用于选择方案
  - 锁定测试集 20%：只用于最终比较，不用于调参

约束：同一 intent_id 的所有变体必须位于同一集合
```

### 2.3 版本快照信息（FR-DS-003）

**dataset_version 表：**

| 字段 | 类型 | 说明 |
|---|---|---|
| version_id | INT PK | |
| corpus_id | INT FK | |
| version_number | VARCHAR | v1.0.0 |
| status | VARCHAR | draft / frozen / published |
| case_count | INT | |
| coverage_report_id | INT FK | |
| split_config | JSON | {dev: 60%, val: 20%, test: 20%} |
| snapshot_metadata | JSON | 见下方 |
| created_at | DATETIME | |
| frozen_at | DATETIME | |

**snapshot_metadata 内容：**

```json
{
  "corpus_version": "v3",
  "document_versions": {"doc_1": "v1", "doc_2": "v2"},
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

### 3.1 Demo 阶段编辑

```
支持操作：
  - PUT /api/cases/{case_id} → 修改题目/答案/证据/优先级
  - DELETE /api/cases/{case_id} → 标记 retired
  - POST /api/cases/{case_id}/retire → 停用（不参与统计）

编辑后行为：
  - case.review_status 回退到 candidate
  - 自动触发重新质量校验
  - 覆盖率重新计算
```

### 3.2 后续版本完整编辑链（FR-DS-EDIT-001~005）

- 编辑批次（edit_batch）：一次编辑会话含多条增删改，作为一个批次提交
- 版本草案：编辑后生成新草案版本，原版本保留
- 撤销操作：可 revert 到上一草案版本，已发布版本不可撤销
- 编辑审计：所有修改操作留痕（操作人/时间/前后内容/原因/规则编号）

### 3.3 增量更新（FR-DS-INC，后续版本）

```
新增文档后：
  1. 仅重解析/向量化新增文档
  2. EIU 抽取仅对新增 Block
  3. 检查新增 EIU 是否与已有 EIU 冲突/替代
  4. 仅对新增/变化 EIU 补题
  5. 未变化 EIU 的已审核题目直接复用 → 新版本
```

### 3.4 表述替换泛化（FR-DS-GEN，后续版本）

```
用户对某规范问题触发"表述替换"：
  - 同 intent 替换：新表述仍绑原 intent_id，旧变体标记 retired
  - 规范问题本体替换：语义实质变化则新建 intent_id
  - 替换后重跑质量校验 + 治理审核
  - 不重复计覆盖率
```

### 3.5 评测集回流（FR-DS-FB，后续版本）

```
闭环步骤：
  回流（自动失败/人工标注）
  → 归因（FR-DIAG-001/002）
  → 分流（修题队列 / 系统优化队列）
  → 处置（编辑走 FR-DS-EDIT，系统优化走 FR-OPT-001）
  → 重校验
  → 重新评测
  → 新版本
  → 全量回归
  → Error Book 记录前后对比
  → 关闭
```

---

## 4. 目录架构浏览与导出

### 4.1 树形浏览 API（FR-DS-TREE-001）

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
```json
{
  "dataset_version": "v1.0.0",
  "coverage": {...},
  "documents": [
    {
      "document_name": "授信政策.pdf",
      "sections": [
        {
          "section_path": "3.1 基本条件",
          "cases": [...]
        }
      ]
    }
  ]
}
```

**Excel 导出：** 扁平表格 + 按章节筛选列。

### 4.3 空评测集处理（FR-DS-EMPTY）

```
判定条件：
  - EIU 总数 = 0（全部被排除或确无实质内容）
  - 实质文段对账率 = 100%
  - 无"未处理"或"抽取失败且无排除记录"的文段

发布行为：
  - 样本数 = 0
  - EIU 清单版本正常冻结（排除记录完整）
  - 覆盖率标注为 N/A
  - 门禁规则不生效（EIU=0 时覆盖率不适用）

后续操作：
  - 可追加文档 → 重新触发解析→EIU→补题 → 产出含题新版本
```

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
| PUT | `/api/cases/{case_id}` | 手动编辑样本 |
| POST | `/api/cases/{case_id}/retire` | 停用样本 |

---

## 6. Demo 实现清单

- [ ] `dataset_version` 表 + 版本冻结 API（含快照元信息记录）
- [ ] 按 intent_id 哈希拆分 dev/val/test（Demo 仅做 60/20/20 比例拆分）
- [ ] JSONL 扁平导出
- [ ] JSON 目录结构导出
- [ ] 空评测集判定 + 发布逻辑
- [ ] 基础手动编辑 API（PUT /api/cases/{case_id}）
- [ ] （延后）编辑批次与版本草案
- [ ] （延后）增量更新 + 增量 EIU 回写
- [ ] （延后）表述替换泛化
- [ ] （延后）回流工作台 + 回流闭环
- [ ] （延后）Excel 导出
