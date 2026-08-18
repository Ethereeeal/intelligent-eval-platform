# 问答生成平台 — Demo

从文档中自动抽取知识点（EIU），生成可评测的问答对（或导出知识点本身）。平台按《评测集平台业务需求书》V1.3 统一管理三类评测集来源（文档生成 / 直接上传 / 公共评测集库），EIU 是向量化与跨文档知识融合的核心对象。

```
上传文档 → 解析Block → 抽取EIU（规则分类+LLM，含上下文补全预留）→ EIU向量化（FAISS）
→ 覆盖规划 → 生成问答对/导出知识点（证据绑定） → 质量门禁（量化评估+审核） → 版本冻结/评测集组合 → 导出
```

## 项目结构

```
├── modules/                          # 全部源码 + 技术文档（8 模块 + shared）
│   ├── m01_data_foundation/          # 01-数据基础：语料库、文档解析、向量化
│   ├── m02_eiu_coverage/             # 02-EIU 抽取与覆盖规划
│   ├── m03_generation/               # 03-评测集生成：题目+答案+证据
│   ├── m04_quality_governance/       # 04-质量门禁
│   ├── m05_dataset_lifecycle/        # 05-数据集生命周期：版本、导出、编辑、三类来源统一管理
│   ├── m06_feedback_loop/            # 06-评测后数据回流（后续版本）
│   ├── m07_smart_qa/                 # 07-智能问答交互（后续版本）
│   ├── m08_auto_evaluation/          # 08-Agent 评测：待测系统适配、指标、归因、ErrorBook
│   └── shared/                       # 跨模块共享：config、database、main.py
├── deploy/                           # 运维基础设施
├── docs/                             # 跨模块架构文档
├── storage/                          # 运行时数据
└── .github/                          # CI/CD
```

每个模块目录自包含：技术文档（README.md）+ 代码（api/models/schemas/services）+ 前端页面。

## 技术栈

| 层 | 实际技术 |
|---|---|
| 后端 | Python + FastAPI（`modules/shared/main.py`） |
| 数据库 | MySQL（docker: evalforge 库） |
| 存储 | MinIO（docker，原始文件落盘到 `storage/raw/`） |
| 向量索引 | FAISS 单例（进程内；仅 EIU 向量，Block 向量已废弃，见 m01 §2.4） |
| Embedding | BGE-small-zh-v1.5（512 维；EIU 向量化，用于抽取去重与未来跨块/跨文档候选；问答对复用已取消，见 m03 §2.4） |
| Reranker | BGE-reranker-v2-m3 |
| LLM | 可配置（OpenAI 兼容 API，见 `.env`） |
| 前端 | 管理台风格静态页面（`front-end/`，docker: studio 容器托管） |

## 端口约定（重要，避免混淆）

所有服务通过 Docker 栈统一编排（`deploy/docker-compose.yml`）。**不要**再在本地手动起 `python main.py` 或 `http.server` 占用端口，否则会与容器冲突 / 连到旧代码。

| 端口 | 服务 | 容器名 | 用途 | 访问入口 |
|---|---|---|---|---|
| `8000` | 后端 API | `evalforge-backend` | FastAPI 接口（`/api/...`） | — |
| `8080` | 前端 | `evalforge-studio` | 管理台静态页面 | **http://localhost:8080** |
| `3306` | MySQL | `evalforge-mysql` | 元数据库 | — |
| `9000` | MinIO API | `evalforge-minio` | 对象存储 | — |
| `9001` | MinIO Console | `evalforge-minio` | 存储控制台 | http://localhost:9001 |

约定：
- 用户访问系统只用 **`http://localhost:8080`**（前端），后端 `8000` 由前端内部调用，不要直接在浏览器打开。
- 改了 `modules/` 源码后，必须 `docker compose -f deploy/docker-compose.yml build backend && docker compose -f deploy/docker-compose.yml up -d backend` 才能让改动生效（源码是烘焙进镜像的，重启容器不重载源码）。

## Demo 阶段边界

**必做：**
- 文档上传解析 + EIU 抽取（规则优先 + LLM 兜底）+ 覆盖清单
- EIU 向量化（FAISS，P0 改造：EIU 为核心向量化对象）
- 单段题目生成 + 标准答案 + 证据绑定
- 5 项基础质量校验（含问题相关性）+ 覆盖率计算
- 版本冻结 + JSON/JSONL 导出
- 两种输出模式：文档知识点 / 问答对（支持泛化扩写）
- 上传评测集（单轮）+ 质量评估；公共评测集库（预置条目）+ 维度选择；评测集组合选择（m05 §8.22）
- Agent 评测（m08）：mock / OpenAI 兼容适配器批量运行 + 基础指标 + D1–D9 基础归因

**不做：**
- 跨文档/跨段题目、反例/对抗题
- EIU 双通道校验、语义关系抽取、治理审核 Skill
- 多轮评测集完整评分（memory/coherence，阶段 2）；语义评分固定校准集（待确认）
- 智能问答交互（07）、评测后数据回流（06）

## 本地启动

统一用 Docker 栈（端口约定见上表）：

```bash
# 构建并启动全部服务（后端 / 前端 / MySQL / MinIO）
docker compose -f deploy/docker-compose.yml up -d --build

# 仅重启后端（改了 modules/ 源码后）
docker compose -f deploy/docker-compose.yml build backend
docker compose -f deploy/docker-compose.yml up -d backend

# 查看后端日志
docker compose -f deploy/docker-compose.yml logs -f backend
```

启动后访问 **http://localhost:8080**（前端）。

> 注意：源码是烘焙进 backend 镜像的，修改 `modules/` 后必须重新 `build backend`，仅 `restart` 不会加载新代码。

> 安全：Demo 默认无鉴权（`API_TOKEN` 留空）；生产必须设置 `API_TOKEN` 并按需收紧 `CORS_ORIGINS`（见 `deploy/env.example`）。

## 协作方式

- 仓库统一使用 GitHub 管理
- 每个功能对应一个 PR
- 各模块独立目录，跨模块修改前先确认接口
- 每天至少同步一次分支状态，避免长期分叉
