# Data Model

本文件为早期（Demo 起步期）核心数据对象草案。**当前表结构与字段以 `modules/shared/services/database.py` 及 m01–m05 模块 README 为准**；本文件保留作概念关系参考，BRD V1.3 新增对象见文末"后续扩展"。

> 当前实现说明：数据库已由 SQLite 迁移为 MySQL（docker evalforge 库）；EIU 表已新增 `embedding_vector`（EIU 向量化，512 维，BRD V1.3 §5.7）；**corpus 概念已移除**（按「文档/文件夹」维度实现，见 m01 §2.1），下文 corpus 相关表结构与关系图为早期设计留档；`document_block`、`eiu`、`generated_case` 等表结构详见 m01–m05 README。

## 核心表结构

### corpus
- corpus_id (PK)
- name
- description
- domain
- created_by
- created_at
- version

### document
- document_id (PK)
- corpus_id (FK → corpus)
- file_name
- file_type
- file_size
- content_hash
- minio_path
- upload_user
- upload_time
- document_version
- parse_status
- parse_error

### document_block
- block_id (PK)
- document_id (FK → document)
- parent_block_id
- section_path
- page_no
- block_type
- block_text
- start_offset
- end_offset
- metadata_json
- embedding_id

### task_job
- job_id (PK)
- job_type
- target_id
- status
- progress
- error_message
- started_at
- finished_at

### retrieval_query
- query_id (PK)
- question
- corpus_id (FK → corpus)
- top_k
- status
- created_at

### retrieval_result
- result_id (PK)
- query_id (FK → retrieval_query)
- block_id (FK → document_block)
- score
- rank
- source_excerpt
- created_at

### run_log
- log_id (PK)
- job_id (FK → task_job)
- level
- message
- created_at

### chat_session（新增——智能问答会话，Demo 延后）

| 字段 | 类型 | 说明 |
|---|---|---|
| session_id | INT (PK) | 主键 |
| corpus_id | INT (FK) | 关联语料库 |
| created_by | VARCHAR | 创建人 |
| title | VARCHAR | 会话标题 |
| status | VARCHAR | active / archived |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 最后活跃时间 |

### chat_message（新增——对话消息，Demo 延后）

| 字段 | 类型 | 说明 |
|---|---|---|
| message_id | INT (PK) | 主键 |
| session_id | INT (FK) | 关联会话 |
| role | VARCHAR | user / system |
| message_type | VARCHAR | text / document_card / preview_card / task_progress / confirm_card |
| content | JSON | 消息体（结构因 message_type 而异） |
| intent | VARCHAR | 解析后的意图类型 |
| intent_params | JSON | 提取的参数 |
| created_at | DATETIME | 发送时间 |

## 主键关系

```
corpus ──1:N──> document ──1:N──> document_block
corpus ──1:N──> retrieval_query ──1:N──> retrieval_result
corpus ──1:N──> chat_session ──1:N──> chat_message
document ──1:N──> task_job
```

## MinIO 对象组织

- `raw/`：原始文件
- `parsed/`：解析结果 JSON
- `chunks/`：切块结果
- `exports/`：导出文件
- `logs/`：附件日志或调试产物

## FAISS 索引

- EIU 向量为主（`eiu.embedding_vector`，512 维，IndexFlatIP 余弦等价，进程内全库索引、从 MySQL 重建，不落盘）；**Block 向量已废弃**（仅作定位分片，不再向量化）；按文档维度检索，无 corpus 过滤
- 索引版本与模型版本绑定
- 向量主键必须与 MySQL `eiu_id` / `block_id` 可追溯对应

## 后续扩展（BRD V1.3）

| 对象 | 说明 | 关键关系 |
|---|---|---|
| EvidenceItem | EIU 有序证据列表中的单条证据（含角色 `direct`/`qualifier`/`reference`/`conflict`、定位全字段、版本） | 关联 EvaluableUnit（BRD V1.3 §8.3 证据列表化，预留） |
| StatementProvenance | EIU 陈述片段到证据条目的映射（可选增强） | 关联 EIU 与 EvidenceItem |
| UploadedEvalSet | 用户直接上传的 QA 评测集（单轮 `q/a/evidence/dimension`；多轮 `session_id + turns[]`） | 关联维度配置与质量评估结果（FR-DS-SRC-001/002，预留） |
| PublicEvalSet | 组织方预置的公共评测集库条目 | 按可配置维度分类，版本化管理（FR-DS-SRC-004，预留） |
| EvalSetDimension | 评测维度可配置体系 | 关联公共库条目与上传样本 |
| EvalSetComposition | Agent 评测前的评测集组合（单个/维度/多来源合并） | 关联评测运行与审计记录（FR-DS-SRC-005，预留） |

> 说明：以上对象为 BRD V1.3 新增需求的预留设计，尚未建表；落地时以数据库迁移为准。

> 更新（2026-08-18）：评测平台架构调整已落地，新增 8 张表——
> `uploaded_eval_set` / `uploaded_eval_case` / `public_eval_set` / `public_eval_case` / `eval_set_dimension` /
> `eval_set_composition` / `evaluation_run` / `evaluation_case_result` / `error_book_item`，
> 字段定义以 `modules/shared/services/database.py` 为准；上文"预留"表项对应的 UploadedEvalSet /
> PublicEvalSet / EvalSetComposition 等对象已由此实现。
