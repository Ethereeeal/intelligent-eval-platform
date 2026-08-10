# Deploy

本地部署与环境配置目录。

## 目录结构

- `Dockerfile`：backend 镜像构建（Python 3.11-slim，含 torch CPU 版 + 全部依赖）
- `docker-compose.yml`：backend + mysql + minio + studio 服务编排
- `requirements.txt`：Python 依赖清单
- `README.md`：本文件
- `../front-end/`：纯静态前端工作台（nginx 托管，无构建、无后端依赖）

## 构建镜像

```bash
docker compose -f deploy/docker-compose.yml build backend
```

- **构建期不下载任何 BGE 模型权重**：模型由宿主机挂载进容器，运行时本地加载（见下文"BGE 模型"）。
- 依赖安装使用国内镜像源（aliyun / 腾讯云 / 清华），并配置全局 **600s 超时、10 次重试**，
  外加整条 `pip install` 的**外层重试循环**（最多 5 次），以对抗容器内访问
  `pypi.org` / `download.pytorch.org` / `files.pythonhosted.org` 的网络抖动（大轮子常 `ReadTimeout`）。
- `torch` 使用 CPU 专用源 `https://download.pytorch.org/whl/cpu`，避免拉取 CUDA 相关大依赖。

## BGE 模型（必须手动准备）

BGE 模型 **不打包进镜像**，需由使用者手动下载到宿主机根目录 `intelligent-eval-platform/models/`，
再由 `docker-compose.yml` 的 `../models:/app/models` 挂载进容器，运行时本地加载：

| 模型 | 目录 | 用途 |
|---|---|---|
| `BAAI/bge-small-zh-v1.5` | `models/bge-small-zh-v1.5/` | 向量化 / 语义分段 |
| `BAAI/bge-reranker-v2-m3` | `models/bge-reranker-v2-m3/` | 重排（CrossEncoder） |

下载地址与完整目录结构见仓库根目录 `models/README.md`。

> 未放置模型时 backend 仍可启动，但首次调用向量化 / 重排接口会失败
> （`HF_HUB_OFFLINE=1` 下不会联网兜底，以保证可重现性）。

## 关键环境变量（backend）

| 变量 | 说明 |
|---|---|
| `EMBEDDING_MODEL_NAME` | 嵌入模型名（默认 `BAAI/bge-small-zh-v1.5`） |
| `HF_ENDPOINT` | HuggingFace 镜像端点（默认 `https://hf-mirror.com`） |
| `HF_HUB_OFFLINE` | 设为 `1` 时禁止联网，强制本地加载 |
| `LOCAL_MODELS_DIR` | 容器内本地模型根目录（默认 `/app/models`，对应挂载的宿主机 `models/`） |

## 启动

```bash
docker compose -f deploy/docker-compose.yml up -d
```

> 修改代码或更新依赖后，执行 `docker compose -f deploy/docker-compose.yml build backend` 重新构建，
> 再用 `up -d` 重新创建容器。模型文件放好后只需 `restart backend` 即可生效。

## 端口约定（务必遵守）

| 宿主机端口 | 服务 | 容器名 | 说明 |
|---|---|---|---|
| `8000` | 后端 API | `evalforge-backend` | FastAPI（`/api/...`），仅前端内部调用 |
| `8080` | 前端 | `evalforge-studio` | 用户访问入口：**http://localhost:8080** |
| `3306` | MySQL | `evalforge-mysql` | 元数据库 `evalforge` |
| `9000` | MinIO API | `evalforge-minio` | 对象存储 |
| `9001` | MinIO Console | `evalforge-minio` | 存储控制台 http://localhost:9001 |

- 不要在宿主机手动起 `python main.py` / `http.server` 占用 `8000` 等端口，会与容器冲突或连到旧代码。
- 源码烘焙进 `backend` 镜像：改 `modules/` 后必须 `build backend` 再 `up -d`，仅 `restart` 不生效。

## 前端工作台（AI Eval Studio）

纯静态前端，由 `front-end/` 目录（独立构建上下文）下的 `Dockerfile`（nginx 托管）构建为 `studio` 服务，
无需构建步骤、无后端依赖：

```bash
# 单独构建 / 启动
docker compose -f deploy/docker-compose.yml build studio
docker compose -f deploy/docker-compose.yml up -d studio
```

- 容器内监听 80，宿主通过 `http://localhost:8080` 访问。
- 构建上下文已限定为 `front-end/` 目录，仅打包前端静态资源，
  不会把 backend 源码或 `models/` 权重带入镜像。
