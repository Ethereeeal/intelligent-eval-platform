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

- 一个语料库一个索引，或先做单全局索引再按 corpus_id 过滤
- 索引版本与模型版本绑定
- 向量主键必须与 MySQL block_id 可追溯对应
