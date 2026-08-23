# 08 — Agent 评测与后评估

> 覆盖 BRD：9. 自动运行与后评估（9.1 待测系统适配 / 9.2 指标体系 / 9.3 失败归因 / 9.4 失败记录与跨版本复测）
> Demo 状态：必做（mock + OpenAI 兼容适配器、基础答案/运行指标、端到端失败 `E2E` 与运行异常 `D9`、基础 ErrorBook）；平台只负责对冻结评测集上的不同智能体版本复测与比较，不负责调优智能体或在 m08 后修改评测集。

---

## 1. BRD 需求摘要

| 需求编号 | 需求 |
|---|---|
| FR-RUN-001 | 黑盒适配器：传入问题或多轮会话、待测智能体版本/配置标识；返回最终答案、耗时、Token、成本与错误信息 |
| FR-METRIC-001 | 数据集自身质量指标（由 m02/m04 计算，本模块引用汇总） |
| FR-METRIC-002 | 检索指标：Evidence Recall@K / MRR / nDCG@K / 多跳完整召回 |
| FR-METRIC-003 | 答案指标：EM / F1 / 语义相似度 / 要点召回 / 忠实性 / 正确拒答率 |
| FR-METRIC-004 | 运行指标：P50/P95 耗时、Token、成本、错误率，按类型/难度/维度分组 |
| FR-DIAG-001/002 | 黑盒失败记录：端到端失败 `E2E` 或运行异常 `D9`；不对 D1–D8 作伪精确归因 |
| FR-OPT-001/002/003 | 失败记录、跨智能体版本复测与 ErrorBook 聚类；平台不负责智能体调优 |

---

## 2. 模块结构

```
modules/m08_auto_evaluation/
├── api.py                  # /api/evaluation-runs、/api/error-book、/api/adapters
├── schemas.py              # EvaluationRunRequest
└── services/
    ├── adapter.py          # mock / openai_compatible 标准适配器（FR-RUN-001）
    ├── runner.py           # 批量运行编排（异步线程，进度写 evaluation_run）
    ├── metrics.py          # 分层指标：答案 / 分组汇总 / 耗时成本（FR-METRIC）
    ├── diagnosis.py        # E2E/D9 黑盒失败标记（FR-DIAG）
    └── optimization.py     # 黑盒失败说明 + ErrorBook 聚类（FR-OPT）
```

## 3. 适配器（FR-RUN-001）

统一返回结构：`{answer, turn_outputs, retrieved, context, usage{time_ms,tokens,cost}, error}`。

| 适配器 | 说明 | 检索轨迹 |
|---|---|---|
| `mock` | 本地示例回答，无外部依赖（Demo / 离线演示） | retrieved=None（不可诊断检索层） |
| `openai_compatible` | OpenAI 兼容问答接口（question / 多轮 turns），支持 system prompt 配置 | retrieved=None |

- 待测智能体仅返回最终答案；平台无法将其检索内容映射到内部 Block/EIU，因此不计算检索指标，也不判定 D1–D8。
- 多轮：`run_multi` 按 turns 顺序注入对话，非关键轮注入已给历史答案，关键轮（key_turn）由模型回答，用于 memory/coherence 验证。
- **安全**：`adapter_config` 中的 `api_key` 不入库（持久化前剔除，接口回显掩码 `***`）；重跑（retry）不保留密钥，需重新创建运行并传入配置。
- **多轮记录边界**：Demo 仅保存待测系统生成的轮次输出到 `evaluation_case_result.turn_outputs`；完整输入 turns、`session_id` 与逐轮上下文持久化属于生产版本能力。

## 4. 运行与指标

```
POST /api/evaluation-runs {composition_id, adapter, adapter_config}
  → 组合解析为统一输入样本（m05 composition.resolve_composition；文档生成来源必须是 frozen 版本）
  → 异步线程逐题调用适配器
  → score_case（FR-DS-SRC-003 评分口径：短答案精确匹配 / 长答案语义相似度）
  → diagnose（答错标记 E2E；调用异常标记 D9；不推断检索或生成根因）
  → 写 evaluation_case_result + error_book_item
  → 进度 0–100 写 evaluation_run
```

- **Demo 指标**：短答案规范化精确匹配；长答案尝试 BGE 余弦相似度（不可用时回退精确匹配）；按难度/维度/归因汇总通过率，并累计耗时、Token、成本和错误率。
- **Demo 失败记录**：答错统一标记 `E2E`（端到端失败、原因不可定位）；调用异常标记 `D9`。待测智能体不返回可与内部 Block/EIU 比对的检索轨迹，因此 D1–D8 不属于本平台的自动归因范围。
- **跨版本复测**：`POST /api/evaluation-runs/{id}/retry` 仅以原组合和原配置重跑；比较新智能体版本时，使用 `POST /api/evaluation-runs` 创建带新适配器/配置和运行名称的独立记录。比较时应固定同一冻结评测集，并展示总体和分组分数。平台不执行智能体调优，m08 运行结果不驱动评测集修订。

## 5. API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/evaluation-runs` | 发起批量运行（202，异步） |
| GET | `/api/evaluation-runs` | 运行列表 |
| GET | `/api/evaluation-runs/{run_id}` | 运行进度 + 指标汇总 |
| GET | `/api/evaluation-runs/{run_id}/results` | 单题结果 + 分层指标汇总 |
| GET | `/api/evaluation-runs/{run_id}/failures` | 该运行的失败记录（`E2E` 端到端失败或 `D9` 运行异常） |
| POST | `/api/evaluation-runs/{run_id}/retry` | 重跑（新 run，回归比较） |
| GET | `/api/error-book` | ErrorBook 查询（智能体失败诊断与优化分析，支持 diagnosis/status 过滤 + 聚类） |
| GET | `/api/adapters` | 内置适配器清单 |
| POST | `/api/dimensions` | 新增评测维度（m05，可配置体系） |

## 6. Demo 实现清单

- [x] mock / openai_compatible 适配器（`adapter.py`，注册表 + 统一返回结构）
- [x] 批量运行编排（`runner.py`，异步线程 + 进度）
- [x] Demo 指标：规范化精确匹配、尽力语义相似度、难度/维度分组通过率、累计耗时/Token/成本/错误率
- [x] Demo 失败记录：`E2E` 端到端失败与 `D9` 运行异常；不对不可观测的 D1–D8 归因
- [x] 基础 ErrorBook：失败归因、建议映射和按归因聚类
- [x] evaluation_run / evaluation_case_result / error_book_item 表 + 创建及查询 API（ErrorBook 状态处置 API 属于生产版本能力）
- [ ] （生产版本）标准黑盒适配器的智能体版本标识、会话控制和完整多轮会话持久化
- [ ] （生产版本）完整答案与运行指标：数据集质量汇总、F1/数值容差/要点召回/忠实性/引用/拒答、P50/P95 与更多分组
- [ ] （生产版本）完整 ErrorBook 处置/回归字段与跨智能体版本分数比较视图；诊断建议由智能体维护方执行，不在平台内自动调优

## 7. 与 m05 的衔接

- 输入：m05 `composition.resolve_composition` 把三类来源（仅 `frozen` 的文档生成版本 / 上传评测集 / 公共库）解析为统一样本；
- 输出：`GET /api/error-book` 供智能体维护方诊断使用，不驱动评测集回流、修订或平台内自动调优；进入 m08 后评测集保持不变。
- 覆盖门禁：上传评测集 / 公共库不参与 EIU 覆盖率（BRD 决策 3），运行输入以组合后的临时标准化评测集为准。
