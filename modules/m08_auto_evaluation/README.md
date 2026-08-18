# 08 — Agent 评测与后评估

> 覆盖 BRD：9. 自动运行与后评估（9.1 待测系统适配 / 9.2 指标体系 / 9.3 失败归因 / 9.4 优化建议与二轮迭代）
> Demo 状态：必做（mock + OpenAI 兼容适配器、基础指标、D1–D9 基础归因、ErrorBook）

---

## 1. BRD 需求摘要

| 需求编号 | 需求 |
|---|---|
| FR-RUN-001 | 标准适配器：传入问题/语料库/检索参数/会话/模型版本；返回答案/检索文段/上下文/耗时/Token/成本/错误码；多轮传入完整对话过程并保存 |
| FR-METRIC-001 | 数据集自身质量指标（由 m02/m04 计算，本模块引用汇总） |
| FR-METRIC-002 | 检索指标：Evidence Recall@K / MRR / nDCG@K / 多跳完整召回 |
| FR-METRIC-003 | 答案指标：EM / F1 / 语义相似度 / 要点召回 / 忠实性 / 正确拒答率 |
| FR-METRIC-004 | 运行指标：P50/P95 耗时、Token、成本、错误率，按类型/难度/维度分组 |
| FR-DIAG-001/002 | 一级归因 D1–D9 + 归因顺序（先验资料→金标准→解析→召回→上下文→生成→安全格式） |
| FR-OPT-001/002/003 | 可执行优化建议；防过拟合（开发/验证/锁定集与回归）；ErrorBook 聚类 |

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
    ├── diagnosis.py        # D1–D9 基础归因 + 归因顺序（FR-DIAG）
    └── optimization.py     # 优化建议映射 + ErrorBook 聚类（FR-OPT）
```

## 3. 适配器（FR-RUN-001）

统一返回结构：`{answer, turn_outputs, retrieved, context, usage{time_ms,tokens,cost}, error}`。

| 适配器 | 说明 | 检索轨迹 |
|---|---|---|
| `mock` | 本地示例回答，无外部依赖（Demo / 离线演示） | retrieved=None（不可诊断检索层） |
| `openai_compatible` | OpenAI 兼容问答接口（question / 多轮 turns），支持 system prompt 配置 | retrieved=None |

- `retrieved` 为 None 表示待测系统未返回检索轨迹 → 运行报告标记"不可诊断检索层"，不强行归因 D3/D4；
- 多轮：`run_multi` 按 turns 顺序注入对话，非关键轮注入已给历史答案，关键轮（key_turn）由模型回答，用于 memory/coherence 验证。
- **安全**：`adapter_config` 中的 `api_key` 不入库（持久化前剔除，接口回显掩码 `***`）；重跑（retry）不保留密钥，需重新创建运行并传入配置。
- **完整对话保存**：多轮运行的每轮输出保存在 `evaluation_case_result.turn_outputs`（FR-DS-SRC-002：运行记录必须保存完整对话过程，用于归因）。

## 4. 运行与指标

```
POST /api/evaluation-runs {composition_id, adapter, adapter_config}
  → 组合解析为统一输入样本（m05 composition.resolve_composition）
  → 异步线程逐题调用适配器
  → score_case（FR-DS-SRC-003 评分口径：短答案精确匹配 / 长答案语义相似度）
  → diagnose（D1–D9，未返回检索轨迹时不可诊断）
  → 写 evaluation_case_result + error_book_item
  → 进度 0–100 写 evaluation_run
```

- **答案指标**：短答案（数值/日期/条款/拒答）规范化精确匹配；长答案语义相似度（BGE cosine），阈值经固定校准集验证（阶段 2 待确认）；
- **分组汇总**：按难度 / 维度 / 归因分布统计通过率，汇总耗时 / Token / 成本 / 错误率（FR-METRIC-004）；
- **失败归因**：D9 运行异常 → D3 检索未召回（有检索轨迹时）→ D5 答案生成失败；D1/D2/D4/D6/D7/D8 需结合解析/金标准/安全信号（基础版优先覆盖 D3/D5/D9，其余交人工确认）；
- **回归**：`POST /api/evaluation-runs/{id}/retry` 创建新 run，供开发集优化前后对比（FR-OPT-002）。

## 5. API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/evaluation-runs` | 发起批量运行（202，异步） |
| GET | `/api/evaluation-runs` | 运行列表 |
| GET | `/api/evaluation-runs/{run_id}` | 运行进度 + 指标汇总 |
| GET | `/api/evaluation-runs/{run_id}/results` | 单题结果 + 分层指标汇总 |
| GET | `/api/evaluation-runs/{run_id}/failures` | 该运行 D1–D9 归因（ErrorBook） |
| POST | `/api/evaluation-runs/{run_id}/retry` | 重跑（新 run，回归比较） |
| GET | `/api/error-book` | ErrorBook 查询（m06 回流工作台数据源，支持 diagnosis/status 过滤 + 聚类） |
| GET | `/api/adapters` | 内置适配器清单 |
| POST | `/api/dimensions` | 新增评测维度（m05，可配置体系） |

## 6. Demo 实现清单

- [x] mock / openai_compatible 适配器（`adapter.py`，注册表 + 统一返回结构）
- [x] 批量运行编排（`runner.py`，异步线程 + 进度）
- [x] 评分口径（`metrics.py` 复用 m05 `scoring.py`）
- [x] D1–D9 基础归因（`diagnosis.py`，含"不可诊断检索层"处理）
- [x] ErrorBook + 优化建议 + 聚类（`optimization.py`）
- [x] evaluation_run / evaluation_case_result / error_book_item 表 + CRUD（shared/database.py）
- [ ] （阶段 2）检索指标（Recall@K / MRR / nDCG）——待测系统返回检索轨迹时启用
- [ ] （阶段 2）多轮 memory/coherence 完整评分与完整对话过程展示
- [ ] （阶段 2）ErrorBook 聚类自动优化实验；m06 回流工作台 UI 深度集成

## 7. 与 m05 / m06 的衔接

- 输入：m05 `composition.resolve_composition` 把三类来源（文档生成冻结版本 / 上传评测集 / 公共库）解析为统一样本；
- 输出：m06 回流工作台消费 `GET /api/error-book`（失败归因 + 优化建议），修订问答对后生成新版本（m05 freeze）；
- 覆盖门禁：上传评测集 / 公共库不参与 EIU 覆盖率（BRD 决策 3），运行输入以组合后的临时标准化评测集为准。
