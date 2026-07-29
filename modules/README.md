# 问答生成平台 — 模块化技术方案

> 适用版本：Demo V0.2.0 | 对应 BRD：V1.2 | 最后更新：2026-07-26

## 平台定位

本平台是一个**问答生成平台**：从文档中自动抽取知识点（EIU），并生成可评测的问答对（或导出知识点本身）。核心链路：

```
上传文档 → 解析Block → 抽取EIU（知识点） → 覆盖规划 → 生成问答对/导出知识点 → 质量门禁 → 导出
```

**输出两种模式（用户可选）：**
- **知识点模式**：直接输出文档知识点，即 EIU 的自然语言版本（带章节/证据定位，不含题目与答案）。
- **问答对模式**：为每个可出题 EIU 至少生成一道规范问答对（题目+答案+证据），可多角度生成多道相关题；支持**用户直接上传问答对**作为种子。两种来源均可进入**泛化**——扩写/改写出数量更多的相关问题对。

**不是 RAG 问答系统**。检索（向量/关键词/关系索引）是辅助工具，用于 EIU 抽取和跨段发现，不是平台产出物。

## 模块索引

| 模块 | 文档 | 覆盖 BRD 章节 | Demo 状态 |
|---|---|---|---|
| m01_data_foundation | [README](./m01_data_foundation/README.md) | 8.1 语料库与文档接入、8.2 结构化解析、8.4 存储与索引 | 必做 |
| m02_eiu_coverage | [README](./m02_eiu_coverage/README.md) | 8.3 语义理解与知识编译、8.5 覆盖规划 | 必做 |
| m03_generation | [README](./m03_generation/README.md) | 8.6 单段问题生成、8.7 跨段、8.8 改写与泛化、8.11 难度体系 | 必做（单段 + 泛化输出） |
| m04_quality_governance | [README](./m04_quality_governance/README.md) | 8.9 问题质量门禁与治理审核 | 必做（5项基础检查） |
| m05_dataset_lifecycle | [README](./m05_dataset_lifecycle/README.md) | 8.10 版本与数据划分、8.12 事后编辑、8.13 目录浏览与导出、8.14 增量更新、8.15 泛化、8.16 评测集回流、8.17 空评测集处理 | 必做（基础版本+导出） |
| m06_feedback_loop | [README](./m06_feedback_loop/README.md) | 9.（仅回流部分，自动评测不在本平台范围） | Demo 不做（后续版本） |
| m07_smart_qa | [README](./m07_smart_qa/README.md) | 8.19 智能问答交互 | Demo 不做（后续版本） |

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python + FastAPI |
| 数据库 | SQLite（Demo） |
| 存储 | 本地文件系统（Demo） |
| 向量索引 | FAISS（辅助） |
| Embedding | BGE-small-zh-v1.5 |
| LLM | 可配置（OpenAI 兼容 API） |
| 前端 | 管理台风格静态页面 |

## Demo 阶段全局边界

**必做：**
- 文档上传解析 + EIU 抽取（LLM 单通道） + 覆盖清单
- 单段题目生成 + 标准答案 + 证据绑定
- 5 项基础质量校验（含问题相关性） + 覆盖率计算
- 版本冻结 + JSON/JSONL 导出
- 两种输出模式：① 文档知识点（EIU 自然语言版本） ② 问答对（支持泛化扩写）

**不做：**
- 跨文档题目（Demo 不做，方案预留）
- 跨段题目（Demo 延后）；反例/对抗题（延后）
- EIU 双通道校验、语义关系抽取（明确不做）、治理审核 Skill
- 自动评测、失败归因、优化建议（均不在本平台范围）
- 评测后数据回流（06，后续版本）
- 智能问答交互（07，Demo 不做）

## 核心数据实体关系

```
corpus（语料库）
  ├── document（原始文档）
  │     └── block（结构化段落/表格行）
  ├── eiu（可评测信息单元）
  │     └── eval_case（评测样本：题目+答案+证据）
  ├── coverage_report（覆盖报告）
  ├── quality_check_result（质量校验结果）
  └── dataset_version（评测集版本）
```

## 项目结构

```
project-root/
├── modules/                     # 全部源码 + 技术文档
│   ├── shared/                  # 跨模块：config, database, main.py, frontend, scripts
│   ├── m01_data_foundation/     # 01-数据基础（必做）
│   ├── m02_eiu_coverage/        # 02-EIU抽取与覆盖规划（必做）
│   ├── m03_generation/          # 03-评测集生成（必做）
│   ├── m04_quality_governance/  # 04-质量门禁（必做）
│   ├── m05_dataset_lifecycle/   # 05-数据集生命周期（必做）
│   ├── m06_feedback_loop/       # 06-数据回流（后续）
│   └── m07_smart_qa/            # 07-智能问答（后续）
├── deploy/                      # 运维基础设施
├── docs/                        # 跨模块架构文档
├── storage/                     # 运行时数据（gitignore）
└── .github/                     # CI/CD
```

## 启动方式

```bash
python -m uvicorn modules.shared.main:app --reload --host 0.0.0.0 --port 8000
```
