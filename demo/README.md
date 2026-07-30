# Intelligent Eval Platform Demo

这是一个本地 demo 后端，支持文档上传、解析、向量化、检索、EIU 抽取、问答生成和质量校验。

## 目录

- `app/` : FastAPI 后端代码
- `storage/` : 本地存储目录
- `models/` : 数据库模型
- `prompts/` : 生成与校验 Prompt 模板

## 启动

```bash
cd demo
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

## 需要准备

- 本地 embedding 模型（例如 `BAAI/bge-small-zh-v1.5`）
- `storage/raw/` 保存原始上传文件
- `storage/db.sqlite` 保存 SQLite 数据
- `storage/faiss.index` 保存 FAISS 向量索引

## 功能

1. 文档上传与解析
2. 语料库与文档管理
3. Block 存储与 local FAISS 索引
4. EIU 抽取
5. 评测集生成（问答对 + 标准答案 + 证据）
6. 基础质量校验
7. 数据集导出

## 不实现

- 评测后回流功能（第六步可跳过）
- 聊天式智能问答功能
