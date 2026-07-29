# 问答生成平台 — Demo

从文档中自动抽取知识点（EIU），生成可评测的问答对（或导出知识点本身）。

```
上传文档 → 解析Block → 抽取EIU → 覆盖规划 → 生成问答对/导出知识点 → 质量门禁 → 导出
```

## 项目结构

```
├── modules/                          # 全部源码 + 技术文档（7 模块 + shared）
│   ├── m01_data_foundation/          # 01-数据基础：语料库、文档解析、向量化
│   ├── m02_eiu_coverage/             # 02-EIU 抽取与覆盖规划
│   ├── m03_generation/               # 03-评测集生成：题目+答案+证据
│   ├── m04_quality_governance/       # 04-质量门禁
│   ├── m05_dataset_lifecycle/        # 05-数据集生命周期：版本、导出、编辑
│   ├── m06_feedback_loop/            # 06-评测后数据回流（后续版本）
│   ├── m07_smart_qa/                 # 07-智能问答交互（后续版本）
│   └── shared/                       # 跨模块共享：config、database、main.py
├── deploy/                           # 运维基础设施
├── docs/                             # 跨模块架构文档
├── storage/                          # 运行时数据
└── .github/                          # CI/CD
```

每个模块目录自包含：技术文档（README.md）+ 代码（api/models/schemas/services）+ 前端页面。

## 技术栈

| 层 | Demo | 生产 |
|---|---|---|
| 后端 | Python + FastAPI | — |
| 数据库 | SQLite | PostgreSQL |
| 存储 | 本地文件系统 | MinIO |
| 向量索引 | FAISS（辅助） | 向量数据库 |
| Embedding | BGE-small-zh-v1.5 | — |
| LLM | 可配置（OpenAI 兼容 API） | — |
| 前端 | 管理台风格静态页面 | — |

## Demo 阶段边界

**必做：**
- 文档上传解析 + EIU 抽取（LLM 单通道）+ 覆盖清单
- 单段题目生成 + 标准答案 + 证据绑定
- 5 项基础质量校验（含问题相关性）+ 覆盖率计算
- 版本冻结 + JSON/JSONL 导出
- 两种输出模式：文档知识点 / 问答对（支持泛化扩写）

**不做：**
- 跨文档/跨段题目、反例/对抗题
- EIU 双通道校验、语义关系抽取、治理审核 Skill
- 自动评测、失败归因（不在本平台范围）
- 智能问答交互（07）、评测后数据回流（06）

## 本地启动

```bash
# 安装依赖
pip install -e .

# 启动服务
python -m uvicorn modules.shared.main:app --reload --host 0.0.0.0 --port 8000
```

## 协作方式

- 仓库统一使用 GitHub 管理
- 每个功能对应一个 PR
- 各模块独立目录，跨模块修改前先确认接口
- 每天至少同步一次分支状态，避免长期分叉
