# Backend

这是 EvalForge Demo 的后端通路骨架，当前目标是先跑通文档上传、解析、入库和检索。

## 本地启动

先进入 `backend/` 目录，再启动服务：

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

如果要先拉起 MySQL 和 MinIO：

```bash
docker compose -f ../deploy/docker-compose.yml up -d
```

## 当前接入层

- `DatabaseService`：SQLAlchemy 数据访问层，默认使用本地 SQLite 兜底，也可以切换成 MySQL URL。
- `StorageService`：原始文件存储层，当前先落盘到本地 `storage/raw/`，后续可替换为 MinIO。
- `FaissIndexService`：向量索引层，优先使用 FAISS，未安装时会退化为本地内存检索。
- `EmbeddingService`：当前使用确定性哈希向量作为 demo 兜底，后续可替换成 BGE。

## 当前结构

- `app/main.py`：FastAPI 入口
- `app/api/`：接口路由
- `app/core/`：配置
- `app/models/`：领域模型
- `app/schemas/`：请求和响应结构
- `app/services/`：上传、存储、检索、数据库和流水线服务
- `app/utils/`：工具函数

## 下一步

1. 将 SQLite 兜底切换为 MySQL 表读写
2. 将本地文件存储切换为 MinIO
3. 将哈希向量切换为 BGE embedding
4. 把检索结果接入前端页面
