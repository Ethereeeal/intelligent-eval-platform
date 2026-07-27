# API

本文件描述后端接口约定、请求参数和返回格式。

## 接口总览

### 文档接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/documents/upload` | 上传文档 |
| GET  | `/api/documents` | 文档列表 |
| GET  | `/api/documents/{document_id}` | 文档详情 |
| GET  | `/api/documents/{document_id}/blocks` | 文档切块列表 |

### 任务接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/api/jobs/{job_id}` | 任务详情 |
| GET  | `/api/jobs` | 任务列表 |
| POST | `/api/jobs/{job_id}/retry` | 重试任务 |

### 检索接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/retrieval/query` | 执行检索查询 |
| GET  | `/api/retrieval/query/{query_id}` | 查询状态 |
| GET  | `/api/retrieval/query/{query_id}/results` | 查询结果 |

### 智能问答接口（Demo 延后，仅占位）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat/sessions` | 创建对话会话 |
| GET  | `/api/chat/sessions` | 会话列表 |
| GET  | `/api/chat/sessions/{session_id}` | 会话详情与消息 |
| POST | `/api/chat/sessions/{session_id}/messages` | 发送消息 |
| DELETE | `/api/chat/sessions/{session_id}` | 删除会话 |

### 导出接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/exports/dataset` | 导出评测集 |
| GET  | `/api/exports/{export_id}` | 导出状态 |

## 新增接口详情

### POST /api/chat/sessions/{id}/messages

发送对话消息（Demo 阶段返回固定占位回复）。

**请求**:
```json
{
  "content": "帮我上传《2026年授信政策指引》"
}
```

**响应** (Demo 占位):
```json
{
  "message_id": 2,
  "role": "system",
  "message_type": "text",
  "content": {
    "text": "您好！智能问答功能将在第二阶段完整实现..."
  }
}
```
