# EvalForge Demo

本仓库用于实现“智能评测集平台”的本地 Demo 版本，目标是在 3 天内跑通最小闭环，并支持 GitHub 协作开发。

## 项目目标

- 上传专业文档到对象存储
- 完成文档解析、切块和元数据入库
- 使用 BGE 模型生成 embedding
- 使用 FAISS 构建向量检索索引
- 支持问题检索、证据返回和结果展示
- 保留基础任务记录，便于后续迭代

## 技术栈

- 后端：Python
- 数据库：MySQL
- 对象存储：MinIO
- 向量检索：FAISS
- Embedding：BGE 系列模型
- 前端：管理台风格页面
- 协作方式：GitHub + 分支开发 + Pull Request

## 仓库结构

- `backend/`：后端服务、API、业务逻辑
- `frontend/`：前端页面和交互
- `docs/`：架构、接口和说明文档
- `scripts/`：初始化脚本、数据准备和索引构建
- `deploy/`：本地部署与环境配置

## 协作方式

- 仓库统一使用 GitHub 管理
- 所有需求先拆成 Issue，再开发
- 每个功能对应一个 PR
- 三人分别维护各自负责模块，跨模块修改前先确认接口
- 每天至少同步一次分支状态，避免长期分叉

## 当前状态

这是初始版本仓库，后续会逐步补充：

1. 后端项目骨架
2. 前端页面骨架
3. MySQL 初始化脚本
4. MinIO 和 FAISS 本地配置
5. Demo 数据和联调说明

## 启动计划

1. 初始化仓库目录结构
2. 补充本地运行配置
3. 打通文档上传与检索链路
4. 完成前端展示和演示脚本

## 本地启动

后端先进入 `backend/` 目录，再启动服务：

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

如果要先用 Docker 拉起 MySQL 和 MinIO：

```bash
docker compose -f deploy/docker-compose.yml up -d
```

Demo 当前采用本地持久化作为默认兜底，后续会逐步切换成 MySQL、MinIO 和 FAISS 的正式接入。

## 备注

本阶段只做本地 Demo，不做完整生产化能力。重点是把数据链路、证据链路和协作链路先稳定下来。
