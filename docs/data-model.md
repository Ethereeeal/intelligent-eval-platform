# Data Model

本文件描述核心数据对象、表结构和主键关系。

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

### requirement_doc（新增——业务需求书专用）

| 字段 | 类型 | 说明 |
|---|---|---|
| requirement_doc_id | INT (PK) | 主键 |
| corpus_id | INT (FK) | 关联语料库 |
| file_name | VARCHAR | 文件名 |
| file_type | VARCHAR | 文件类型 |
| requirement_version | VARCHAR | 需求文档版本号 |
| business_domain | VARCHAR | 业务领域 |
| author_department | VARCHAR | 编写部门 |
| effective_date | DATE | 生效日期 |
| review_date | DATE | 评审日期 |
| uploaded_at | DATETIME | 上传时间 |
| parse_status | VARCHAR | 解析状态 |

### test_function_point（新增——测试功能点 / EIU 子类型）

| 字段 | 类型 | 说明 |
|---|---|---|
| tfp_id | INT (PK) | 主键 |
| requirement_doc_id | INT (FK) | 关联需求书 |
| section_path | VARCHAR | 所属章节路径 |
| requirement_id | VARCHAR | 原始需求编号（如 FR-LOGIN-001） |
| statement | TEXT | 功能点完整陈述 |
| eiu_type | VARCHAR | functional_rule / business_rule / data_rule / interface_rule / nfr |
| content_priority | VARCHAR | P0 / P1 / P2 |
| weight | INT | 权重（P0=5, P1=3, P2=1） |
| evidence_range | JSON | 原文定位信息 |
| is_questionable | BOOLEAN | 是否可出题 |
| exclusion_reason | VARCHAR | 排除原因 |
| extraction_model | VARCHAR | 提取模型名称 |
| extraction_confidence | FLOAT | 提取置信度 |
| review_status | VARCHAR | 审核状态 |
| governance_skill_version | VARCHAR | 审核 Skill 版本 |
| created_at | DATETIME | 创建时间 |

**注意：** `test_function_point` 与问答评测集的 EIU 核心区别——不含 `gold_answer`、`must_have_points`、`acceptable_answers` 等答案字段。该表记录的是"需要验证什么"，而非"正确答案是什么"。

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
corpus ──1:N──> requirement_doc ──1:N──> test_function_point
corpus ──1:N──> retrieval_query ──1:N──> retrieval_result
corpus ──1:N──> chat_session ──1:N──> chat_message
document ──1:N──> task_job
```

## MinIO 对象组织

- `raw/`：原始文件（含需求书）
- `parsed/`：解析结果 JSON
- `chunks/`：切块结果
- `exports/`：导出文件（含测试功能点导出）
- `logs/`：附件日志或调试产物

## FAISS 索引

- 一个语料库一个索引，或先做单全局索引再按 corpus_id 过滤
- 索引版本与模型版本绑定
- 向量主键必须与 MySQL block_id 可追溯对应
