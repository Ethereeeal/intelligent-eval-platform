# 08 — Agent 评测与后评估

> 覆盖 BRD：9. 自动运行与后评估（9.1 待测系统适配 / 9.2 指标体系 / 9.3 失败归因 / 9.4 失败记录与跨版本复测）
> Demo 状态：必做（mock + OpenAI 兼容 + 通用 HTTP 适配器、基础答案/运行指标、可选中间节点评测、端到端失败 `E2E` 与运行异常 `D9`、基础 ErrorBook）；平台只负责对冻结评测集上的不同智能体版本复测与比较，不负责调优智能体或在 m08 后修改评测集。
>
> 多轮第一版口径：先选择已有的标准答案评测集，再调用目标智能体；最终轮沿用现有精确/语义评分做错误初筛，只有失败或不确定样本才需要结合前置对话分析。这个最小闭环不依赖 Langfuse，也不要求 `key_turn`、`turn_type`、`depends_on_turns` 成为必填字段；完整逐轮 `memory/coherence` 评分仍属于后续能力。

---

## 1. BRD 需求摘要

| 需求编号 | 需求 |
|---|---|
| FR-RUN-001 | 黑盒适配器：传入问题或多轮会话、待测智能体版本/配置标识；返回最终答案、耗时、Token、成本与错误信息 |
| FR-METRIC-001 | 数据集自身质量指标（由 m02/m04 计算，本模块引用汇总） |
| FR-METRIC-002 | 可选中间节点评测：改写、意图分类、RAG；节点内指标固定，不绑定平台内部 Block / EIU |
| FR-METRIC-003 | 最终答案指标：规范化精确匹配 / 语义相似度 / 正确拒答率 |
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
    ├── adapter.py          # mock / openai_compatible / http 标准适配器（FR-RUN-001）
    ├── runner.py           # 批量运行编排（异步线程，进度写 evaluation_run）
    ├── metrics.py          # 分层指标：答案 / 分组汇总 / 耗时成本（FR-METRIC）
    ├── intermediate_metrics.py # rewrite / intent / RAG 固定中间节点指标
    ├── diagnosis.py        # E2E/D9 黑盒失败标记（FR-DIAG）
    └── optimization.py     # 黑盒失败说明 + ErrorBook 聚类（FR-OPT）
```

## 3. 适配器（FR-RUN-001）

统一返回结构：`{answer, turn_outputs, retrieved, node_outputs, context, turn_trace, usage{time_ms,tokens,cost}, error}`。

| 适配器 | 说明 | 检索轨迹 |
|---|---|---|
| `mock` | 本地示例回答，无外部依赖（Demo / 离线演示） | retrieved=None（不可诊断检索层） |
| `openai_compatible` | OpenAI 兼容问答接口（question / 多轮 turns），支持 system prompt 配置 | retrieved=None |
| `http` | 通用 HTTP；可配置 `retrieved_path`、`node_outputs_path` 读取外部智能体返回的检索文本和节点输出 | 按路径读取 |

- 待测智能体只返回最终答案时，平台没有中间节点数据，所选中间节点记为 `data_missing`，不把缺失当作 0 分。平台不要求把外部智能体的切块映射到内部 Block/EIU，也不判定 D1–D8。
- 多轮最小闭环：`run_multi` 按 `turns[]` 顺序构造请求，把已有问答作为固定历史上下文，最后一轮调用目标智能体并用该轮标准答案评分。`key_turn`、`turn_type`、`depends_on_turns` 可以作为高级标注保留，但不是基本评测前置条件。
- 中间节点评测是运行级可选项，运行时可选择 `rewrite`、`intent`、`rag`；节点内指标固定，不提供逐项勾选。`intent` 只评估意图分类，不评估参数槽位。
- `rewrite` 固定计算语义相似度；存在约束标注时追加约束 Precision / Recall / F1 和完整保持率，没有约束标注时只计算语义相似度。`intent` 只比较标准意图标签与实际意图标签，不引入不通用的参数槽位指标。`rag` 固定使用 RAGAS Context Precision、Context Recall、Faithfulness、Answer Relevancy 四项指标。
- RAG 只需要评测集问题/标准答案和待测智能体实际返回的检索文本；外部评测集也可以使用，不依赖平台内部 Block、EIU 或 `source_ref`，也不要求只有一个正确检索片段。没有实际检索文本时，RAG 节点记为 `data_missing`。
- HTTP 适配器可在响应中配置 `retrieved_path` 和 `node_outputs_path`；前者读取实际检索片段，后者读取 `rewrite` / `intent` / `rag` 节点输出。适配器只做字段路径映射，不假设不同智能体的节点返回格式相同。
- **安全**：`adapter_config` 中的 `api_key` 不入库（持久化前剔除，接口回显掩码 `***`）；单题复测需重新提交敏感配置，前端复用模板也不保存 API Key 或 Header 值。运行时若需做上下文分析，只允许使用本次评测实际发送给目标智能体的对话内容。
- **多轮记录边界**：运行结果保存 `input_turns`、待测系统生成的 `turn_outputs` 和逐轮 `turn_trace`（实际请求消息、响应、轮次索引及是否调用目标智能体）；失败或未评分样本可在结果详情中保存 `context_analysis`。不能用评测集中的标准答案替代目标智能体实际收到的上下文。

## 4. 运行与指标

```
POST /api/evaluation-runs {composition_id, adapter, adapter_config, intermediate_eval?}
  → 组合解析为统一输入样本（m05 composition.resolve_composition；文档生成来源必须是 frozen 版本）
  → 异步线程逐题调用适配器
  → score_case（FR-DS-SRC-003 评分口径：短答案精确匹配 / 长答案语义相似度）
  → 多轮失败/未评分样本保留前置对话，供人工上下文分析
  → diagnose（答错标记 E2E；调用异常标记 D9；不推断检索或生成根因）
  → 写 evaluation_case_result + error_book_item
  → 进度 0–100 写 evaluation_run
```

中间评测配置示例：

```json
{
  "enabled": true,
  "nodes": ["intent", "rag"]
}
```

`intermediate_eval` 缺省或关闭时完全沿用旧的最终答案评测流程。每条结果的中间分数写入
`scores.intermediate`，运行选择写入 `evaluation_run.intermediate_eval`；历史运行缺少该字段时按关闭处理。

### 4.1 中间节点评测口径

中间节点评测是一次运行的附加评测，不改变最终答案的通过/失败判定。前端只让用户选择是否启用以及节点类型；选中节点后使用以下固定指标：

| 节点 | 必要输入 | 固定输出 |
|---|---|---|
| `rewrite` 改写 | 标准改写文本、实际改写文本；可选约束列表 | 语义相似度；有约束时增加约束 Precision / Recall / F1、完整保持率 |
| `intent` 意图分类 | 标准意图标签、实际意图标签 | 单题正确与否；运行汇总 Accuracy、Macro-F1、各标签 Precision / Recall / F1、混淆矩阵 |
| `rag` | 问题、标准答案、实际回答、实际检索文本列表 | RAGAS Context Precision、Context Recall、Faithfulness、Answer Relevancy |

输入字段通过评测样本的 `intermediate_reference` / `node_contract` 传递。外部评测集可以只提供它能提供的字段；缺少某个节点的标准数据、实际节点输出或实际检索文本时，该节点状态为 `data_missing`，指标保持 `null`，不参与均值计算。RAGAS 依赖未安装、评测模型未配置或调用失败时分别返回 `unavailable` / `error`，不伪造 0 分。

- **Demo 指标**：短答案规范化精确匹配；长答案尝试 BGE 余弦相似度（不可用时回退精确匹配）；按难度/维度/归因汇总通过率，并累计耗时、Token、成本和错误率。
- **Demo 失败记录**：答错统一标记 `E2E`（端到端失败、原因不可定位）；调用异常标记 `D9`。待测智能体不返回可与内部 Block/EIU 比对的检索轨迹，因此 D1–D8 不属于本平台的自动归因范围。
- **复测与对比**：单题复测通过 `POST /api/evaluation-results/{id}/retry` 创建关联尝试，不覆盖原结果；只有达到发起复测时的分析阈值才自动把异常项置为 `verified`。运行对比固定同一评测集版本，展示新增失败、已修复和持续失败。平台不执行智能体调优，m08 运行结果不驱动评测集修订。
- **可观察说明**：后端保留 `E2E` / `D9` 诊断代码用于审计，前端默认显示“答案未通过”或“调用异常”，避免把内部编码直接暴露给测试人员。

### 4.2 最简多轮评测流程

多轮评测不是“先从错误记录反推评测集”。正确顺序是：

1. 在评测运行页选择已有的多轮标准答案评测集；评测集本身包含问题、标准答案和可选的前置对话。
2. m08 按顺序把前置对话发送给目标智能体，并在目标轮获取实际回复。
3. 先用现有规范化精确匹配或语义相似度比较目标轮回复与标准答案，得到通过、失败或待分析候选。
4. 对失败或不确定候选展示本次请求的完整前置对话，再判断是记忆失败、当前回答矛盾、约束违反，还是普通答案错误。
5. 将分析结果写入运行结果/ErrorBook；确认具有长期回归价值后，再人工整理为新的多轮回归样本。

因此，“错误筛查”发生在一次评测运行之内：标准答案评测集先被选中，目标智能体回复产生后才进行语义初筛；上下文用于解释错误，不用于替代标准答案，也不要求首轮就人工寻找错误。

## 5. API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/evaluation-runs` | 发起批量运行（202，异步） |
| GET | `/api/evaluation-runs` | 运行列表 |
| GET | `/api/evaluation-runs/{run_id}` | 运行进度 + 指标汇总 |
| GET | `/api/evaluation-runs/{run_id}/results` | 单题结果 + 分层指标汇总 |
| POST | `/api/evaluation-runs/{run_id}/cancel` | 取消运行；当前单题请求结束后收敛为 `cancelled` |
| DELETE | `/api/evaluation-runs/{run_id}?confirm=true` | 永久删除终态运行及关联结果；运行中禁止删除 |
| POST | `/api/evaluation-runs/{run_id}/export` | 导出 Excel 原始报告；`result_ids` 为空时导出全部，传入列表时导出筛选结果 |
| GET | `/api/evaluation-runs/{run_id}/failures` | 该运行的失败记录（`E2E` 端到端失败或 `D9` 运行异常） |
| POST | `/api/evaluation-runs/{run_id}/retry` | 重跑（新 run，回归比较） |
| GET | `/api/evaluation-results/{result_id}/attempts` | 原始结果及其单题复测尝试链 |
| POST | `/api/evaluation-results/{result_id}/retry` | 发起单题复测（202，不覆盖原结果） |
| GET | `/api/error-book` | ErrorBook 查询（智能体失败诊断与优化分析，支持 diagnosis/status 过滤 + 聚类） |
| PATCH | `/api/error-book/{item_id}` | 标记待处理、已处理待复测或忽略；`verified` 仅由复测通过写入 |
| GET | `/api/adapters` | 内置适配器清单 |
| POST | `/api/adapters/test` | 使用单条问题测试目标智能体通路，不持久化敏感配置 |
| POST | `/api/dimensions` | 新增评测维度（m05，可配置体系） |

## 6. Demo 实现清单

- [x] mock / openai_compatible / http 适配器（`adapter.py`，注册表 + 统一返回结构）
- [x] 批量运行编排（`runner.py`，异步线程 + 进度）
- [x] Demo 指标：规范化精确匹配、尽力语义相似度、难度/维度分组通过率、累计耗时/Token/成本/错误率
- [x] Demo 失败记录：`E2E` 端到端失败与 `D9` 运行异常；不对不可观测的 D1–D8 归因
- [x] 基础 ErrorBook：失败归因、建议映射和按归因聚类
- [x] evaluation_run / evaluation_case_result / error_book_item 表 + 创建及查询 API
- [x] 运行取消与终态强确认删除、ErrorBook 人工处置、单题复测尝试链和同版本前端对比
- [x] 运行级可选中间节点评测：`rewrite`、`intent`、`rag`；节点内指标固定，缺失数据不按 0 分计入汇总
- [x] RAGAS 四项指标接入：Context Precision、Context Recall、Faithfulness、Answer Relevancy；支持外部评测集和外部智能体返回的原始检索文本
- [x] 通用 HTTP 适配器支持 `retrieved_path` / `node_outputs_path`，将外部响应映射到统一中间节点输入
- [x] （多轮第一版）保存目标智能体实际收到的逐轮请求上下文，并在失败/不确定结果中可回看前置对话
- [x] （多轮第一版）在基线精确/语义评分之后增加上下文错误分析入口；分析结果不覆盖原始评分
- [ ] （后续版本）按轮次计算 memory/coherence，并支持更细的人工抽查与 Judge 校准
- [ ] （生产版本）标准黑盒适配器的智能体版本标识、会话控制和完整多轮会话持久化
- [ ] （生产版本）完整答案与运行指标：数据集质量汇总、F1/数值容差/要点召回/忠实性/引用/拒答、P50/P95 与更多分组
- [ ] （生产版本）ErrorBook 负责人/权限/批量处置、持久化凭据服务与评分策略版本化；诊断建议由智能体维护方执行，不在平台内自动调优

## 7. 与 m05 的衔接

- 输入：m05 `composition.resolve_composition` 把三类来源（仅 `frozen` 的文档生成版本 / 上传评测集 / 公共库）解析为统一样本；已有标准答案评测集是多轮运行的入口，不从 ErrorBook 反向生成首次运行输入。中间节点评测所需的标准标签/文本随样本的 `intermediate_reference` / `node_contract` 传递。
- 输出：`GET /api/error-book` 供智能体维护方诊断使用，不驱动评测集回流、修订或平台内自动调优；进入 m08 后评测集保持不变。
- 覆盖门禁：上传评测集 / 公共库不参与 EIU 覆盖率（BRD 决策 3），运行输入以组合后的临时标准化评测集为准。
