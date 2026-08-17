# 02 — EIU 抽取与覆盖规划

> 覆盖 BRD：8.3 语义理解与知识编译 / 8.5 覆盖规划
> Demo 状态：必做（LLM 单通道抽取 + 覆盖计算）

---

## 1. BRD 需求摘要

### 8.3 语义理解与知识编译

| 需求编号 | 需求 |
|---|---|
| FR-SEM-001 | 每个底层文段生成上下文说明（所属文档/章节/主体/期间/主题），与原文共同向量化 |
| FR-SEM-002 | 按段落/小节/章节/文档生成层级摘要，标记模型版本，不能替代底层原文 |
| FR-SEM-003 | EIU 抽取：将段落拆为可评测信息单元，逐条结构化记录，EIU 类型含定义/适用范围/规则/阈值/例外/日期/指标/公式/流程/变更 |
| FR-SEM-004 | EIU 拆分与计数规则（8 条）：独立真值/限定语不可脱离/例外单列/定义公式分列/表格业务行/无实质不计数/重复合并/不可回答排除 |
| FR-SEM-005 | 术语和财务指标消歧：规范名称/别名/定义/公式/分子分母/主体/口径/期间/币种 |

### 8.5 覆盖规划

| 需求编号 | 需求 |
|---|---|
| FR-COVER-001 | 生成覆盖清单：按文档/章节/EIU类型/优先级/单段跨段/难度等维度统计 |
| FR-COVER-002 | 加权 EIU 覆盖率公式：Σ(w_i×c_i)/Σ(w_i)，P0=5/P1=3/P2=1 |
| FR-COVER-003 | 防止覆盖率失真：不能计假覆盖、不能排除难以生成题目的 EIU |
| FR-COVER-004 | 多角度覆盖：一个 EIU 可从不同角度生成多道相关题作为增强；覆盖率按 EIU 是否≥1 题计（c_i=1），多角度题不重复计分母 |

---

## 2. EIU 抽取技术方案

### 2.1 EIU 定义回顾

EIU (Evaluable Information Unit) = 一条能够被原文**独立证明或否定**、并能够形成**明确问题与答案**的最小业务陈述。

**10 种 EIU 类型：**

| 类型 | 英文 | 识别特征 | 示例 | 后续题目类型 |
|---|---|---|---|---|
| 定义 | definition | "X是指……""X包括……" | "净利润率是指净利润与营业收入的比率" | 定义题 |
| 规则 | rule | "……应当……""……不得……" | "小微企业申请贷款时资产负债率不得超过70%" | 条件与适用范围题 |
| 阈值 | threshold | 数值、百分比、上下限 | "资产负债率上限为70%" | 阈值和数值题 |
| 日期 | date | 生效/失效/过渡日期 | "本规定自2026年8月1日起施行" | 时效题 |
| 公式 | formula | 计算方式、变量关系 | "净利润率 = 净利润 / 营业收入 × 100%" | 公式与计算题 |
| 流程 | process | 步骤序列 | "贷款审批流程：受理→调查→审查→审批→放款" | 流程顺序题 |
| 例外 | exception | "除非……""……除外""……可以放宽" | "政策性担保全额担保的，可放宽至75%" | 例外与边界题 |
| 禁止 | prohibition | "禁止……""不得……""严禁……" | "不得向关联方发放无担保信用贷款" | 是否可回答题 |
| 指标 | metric | 带主体/期间/币种/单位的指标值 | "2025年净利润为1,000万元" | 事实提取题 |
| 变更 | change | 版本对比、新旧更替 | "2026版将资产负债率上限从75%调整为70%" | 比较与区分题 |

### 2.2 EIU 拆分规则（FR-SEM-004）

```
原文：小微企业申请流动资金贷款时，资产负债率原则上不得超过70%；
      由政策性担保机构提供全额担保的，可放宽至75%。
      本规定自2026年8月1日起施行。

拆分结果：
  EIU-1 [rule/threshold P0] 小微企业申请流动资金贷款时，资产负债率原则上不得超过70%
  EIU-2 [exception/threshold P0] 由政策性担保机构提供全额担保时，资产负债率上限可放宽至75%
  EIU-3 [date P1] 该规定自2026年8月1日起施行
```

**8 条拆分规则：**

| # | 规则 | 含义 |
|---|---|---|
| 1 | 独立真值 | 两项可分别判断真伪 → 必须拆为两个 EIU |
| 2 | 限定语不可脱离 | 主体/条件/范围/期间/币种/单位必须与结论在同一 EIU 中 |
| 3 | 例外单列 | 一般规则与例外规则分别计数 |
| 4 | 定义公式分列 | 定义/公式/变量口径/示例数值分别计数 |
| 5 | 表格业务行 | 以"指标+主体+期间+单位+数值"完整记录为一个 EIU |
| 6 | 无实质不计数 | 标题/目录/过渡句/页眉页脚/重复免责声明 → 不计数 |
| 7 | 重复合并 | 同一事实多处出现 → 分母只保留一个规范 EIU，多证据引用 |
| 8 | 不可回答排除 | 证据残缺/OCR无法确认 → 不进入分母，记录排除原因 |

### 2.3 Demo EIU 抽取实现（LLM 单通道）

**流程：**

```
对每个 Block：
  1. 预处理：跳过纯标题/目录/页眉页脚（规则过滤）
  2. 组装上下文：
     - 文档名 + 章节路径 + 页码
     - 当前 Block 文本
     - 前一个 Block 文本（提供上下文衔接）
     - 后一个 Block 文本
  3. 调用 LLM，传入 EIU 抽取 Prompt
  4. 解析 LLM 返回的 JSON 数组
  5. 将每条 EIU 写入 eiu 表，绑定源 block_id
```

**Prompt 设计核心要素：**

```
系统角色：授信政策和财务报告分析专家

任务：
1. 判断该段落是否包含实质内容
2. 将实质内容按 8 条拆分规则拆为 EIU
3. 每个 EIU 标注：完整陈述/类型/优先级/限定信息/是否可出题

优先级定义：
- P0：监管禁止事项、关键阈值、例外条款、安全边界
- P1：核心定义、主流程、核心指标和公式
- P2：一般说明和补充事实

输出格式：JSON 数组
```

**EIU 数据模型（eiu 表）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| eiu_id | INT PK | |
| corpus_id | INT FK | |
| block_id | INT FK | 源 Block |
| statement | TEXT | 完整陈述（一句话，可独立判定真伪） |
| eiu_type | VARCHAR | definition/rule/threshold/date/formula/process/exception/prohibition/metric/change |
| content_priority | VARCHAR | P0/P1/P2 |
| weight | INT | 5/3/1 |
| constraints_json | JSON | {主体,条件,范围,期间,币种,单位} |
| evidence_blocks | JSON | [block_id, ...] |
| is_questionable | BOOL | 是否可出题 |
| exclusion_reason | VARCHAR | 不可出题原因 |
| extraction_model | VARCHAR | LLM 模型名称+版本 |
| extraction_confidence | FLOAT | 0-1 |
| review_status | VARCHAR | candidate / quality_verified / blocked |
| created_at | DATETIME | |

**文档更新自动重抽（FR-CORPUS-004，覆盖式全量重算，进度由 doc_update_job 承载）：**
- 重传触发后，先删除该文档旧版本的全部 block/向量/EIU/题目（整体作废），再全量重新分段 + BGE 向量化 + 抽 EIU。Demo 不做增量：BGE 语义分段会使 Block 边界随上下文偏移，难以可靠定位"哪些 Block 变了"，全量重算更简单稳妥。
- 抽取进度通过 job 的 `progress` 反馈：progress = 已抽 Block 数 / 总 Block 数。
- 写库后由 05 §3.3 覆盖重建逻辑整体替换该文档的 EIU 与题面，不做 `superseded/conflicted/deprecated` 旧版本残留。
- 抽取全程异步，前端以 job 进度为准，不阻塞其他操作。

**已知限制（设计确认）：表格逐行切散**

表格/结构化数据（`excel_row` / `table` 块）在解析时**按行切成独立 block**，跨行才完整的业务规则（如"某类主体+适用条件+限制值"分列在多行）会被切散。当前靠 `_build_neighbors`（前后各 1 个 block 文本）作为上下文补救，但跨多行的规则仍可能抽取不全或拆成多条 EIU。

- **现状**：纯文本段落已由 parser 的相邻连续段落合并缓解（接近自然段落），表格/行切散仍是已知限制。
- **影响**：表格类文档的知识点抽取可能漏抽/拆散，进而影响该文档的覆盖与出题完整度。
- **预留方案（Demo 不实现）**：以"章节/表头+行"为抽取单元，或将整张表（表头+全部行）作为单次抽取输入，替代"逐行切块"。抽取去重阈值 `SEMANTIC_DEDUP_THRESHOLD=0.90` 偏紧，同义知识点（措辞不同，相似度约 0.85~0.90）可能漏判重复，预留为按真实分布标定调整。

### 2.4 Demo 不做但技术方案预留

**术语消歧（FR-SEM-006，后续版本）：**

为每个被识别为指标/公式的 EIU 补充 `term` 记录：

| 字段 | 说明 |
|---|---|
| canonical_name | 规范名称（如"净利润率"） |
| aliases | 别名列表 |
| definition | 业务定义 |
| formula | 计算公式 |
| numerator/denominator | 分子/分母 |
| entity | 主体（合并/单体） |
| period | 报告期间 |
| currency | 币种 |
| unit | 单位 |
| easily_confused_with | 容易混淆的术语列表 |

**跨块 / 跨文档题（设计确认，Demo 不实现）：**

跨块题包含两种形态，均需 EIU 向量 + FAISS 候选召回支撑：

| 形态 | 定义 | 示例 |
|---|---|---|
| 跨块题（单文档跨段） | 同一文档内，多个 EIU 组合成一道题 | 规则 + 例外、定义 + 公式 |
| 跨文档题 | 不同文档的 EIU 拼接组合 | 文档 A 的定义 + 文档 B 的计算公式 |

**跨文档去重策略（做跨文档题时自动执行）：**

做跨文档题时，先自动去除跨文档重复的 EIU，再拼接互补的 EIU：
- **完全一致**：归一化哈希一致 → 自动去（保留一份）
- **重复很高**：EIU 向量余弦 ≥ 0.92（语义几乎相同）→ 自动去
- **互补（适度相似但类型互补，如 rule × exception）**：保留，用于拼接

判定时需区分"重复"（该合并）与"互补"（该拼接）——高相似 = 重复去重；
适度相似 + 类型互补（白名单 pair） = 拼接候选。

> 依赖：EIU 向量落库（`eiu.embedding_vector`）+ FAISS 检索（`EiuFaissIndex`）为此预留，
> 当前仅用于抽取去重与复用，跨块/跨文档候选召回为未来用途。

**抽取忠实度校验（设计确认，Demo 不实现）：**

当前 `normalize_item` 仅做**字段/格式校验**（类型合法、长度、confidence 夹取、必填字段），
**未校验内容忠实性**：
- ❌ statement 是否忠于原文（可能 LLM 幻觉 / 擅自增删限定语、改数值）
- ❌ `eiu_type` 分类是否正确（规则误判 LLM 兜底句）
- ❌ `constraints` 约束抽取是否忠于原文

预留方案（后续版本，二选一或叠加）：
- **轻量回读校验**：把 statement 回原文找证据，找不到对应片段 → 标记"疑似幻觉"，降级或排除。
  成本低，直接防 LLM 幻觉。
- **双通道交叉验证（FR-SEM-005 预留）**：两次独立抽取比对，不一致交由人工；成本高、
  "LLM 评 LLM"有偏置，故未在 Demo 启用。

> 当前依赖 `extraction_confidence`（LLM 自评），非独立校验。优先级低于评测时 m04 质检兜底。

---

## 3. 覆盖规划技术方案

### 3.1 覆盖清单（FR-COVER-001）

**统计维度：**
- 按文档分组
- 按章节（section_path）分组
- 按 EIU 类型分组
- 按优先级（P0/P1/P2）分组
- 按单段/跨段分组
- 按难度（L1/L2/L3）分组

**输出示例：**

```json
{
  "corpus_id": 1,
  "total_eiu": 127,
  "questionable_eiu": 118,
  "excluded_eiu": 9,
  "by_priority": { "P0": 32, "P1": 61, "P2": 34 },
  "by_type": { "rule": 28, "threshold": 22, "definition": 19, ... },
  "by_document": [
    { "document_name": "授信政策.pdf", "eiu_count": 85 },
    { "document_name": "附件表格.xlsx", "eiu_count": 42 }
  ],
  "gaps": [
    { "eiu_id": 42, "statement": "...", "reason": "暂无对应题目" }
  ]
}
```

### 3.2 加权覆盖率计算（FR-COVER-002）

```
设 K = 当前语料库版本中已通过审核、可出题的 EIU 集合
w_i: P0=5, P1=3, P2=1
c_i: 1（已有通过质量校验的规范问题），0（未覆盖）

WeightedCoverage = Σ(w_i × c_i) / Σ(w_i)
```

**代码实现（确定性计算，不依赖 LLM）：**

```python
def calculate_weighted_coverage(eius: list[EIU], cases: list[EvalCase]) -> CoverageReport:
    covered_eiu_ids = {c.eiu_id for c in cases if c.review_status == "quality_verified"}
    total_weight = 0
    covered_weight = 0
    p0_total, p0_covered = 0, 0

    for eiu in eius:
        if not eiu.is_questionable:
            continue  # 排除项不计入分母
        w = eiu.weight
        total_weight += w
        if eiu.content_priority == "P0":
            p0_total += 1
        if eiu.eiu_id in covered_eiu_ids:
            covered_weight += w
            if eiu.content_priority == "P0":
                p0_covered += 1

    return CoverageReport(
        total_eiu_count=len(eius),
        questionable_count=sum(1 for e in eius if e.is_questionable),
        excluded_count=sum(1 for e in eius if not e.is_questionable),
        weighted_coverage=covered_weight / total_weight if total_weight > 0 else 0,
        p0_coverage=p0_covered / p0_total if p0_total > 0 else 1.0,
        ...
    )
```

### 3.3 防止覆盖率失真（FR-COVER-003）

以下情况**不计为有效覆盖**，在代码中通过规则 + LLM 辅助检查：

| 失真类型 | 检测方式 |
|---|---|
| 只有问题、没有可验证答案 | 规则：检查 case.gold_answer 非空 |
| 答案来自模型常识非原文 | LLM：在质量校验"忠实性"检查中检测 |
| 证据只支持答案的一部分 | LLM：在质量校验"证据充分性"检查中检测 |
| 问题包含答案暗示 | LLM：在质量校验"唯一性"检查中检测 |
| 多个改写重复计算 | 规则：按 intent_id 去重（Demo 不做改写，此条沿用） |
| 多角度题重复计算 | 规则：按 eiu_id 计覆盖，同一 EIU 的多角度题只计一次（c_i=1），不重复计入分母 |
| 覆盖率分母被人为排空 | 规则：检查排除记录中的 exclusion_reason，拒绝"因题目难生成"类排除 |

**业务门禁（硬性规则，代码强制执行）：**
- 总体加权 EIU 覆盖率 < 85% → 阻断发布
- P0 EIU 覆盖率 < 100% → 阻断发布
- 实质 Block 对账率 < 100% → 阻断发布（每个 Block 必须有 EIU 或排除记录）

---

## 4. API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/corpus/{corpus_id}/eiu/extract` | 触发 EIU 抽取（异步，进度见 doc_update_job） |
| GET | `/api/jobs/{job_id}` | 查询抽取/更新任务进度与状态（贯穿解析→抽取→增量） |
| GET | `/api/corpus/{corpus_id}/eiu` | EIU 清单（支持 ?type=&priority=&section=&questionable= 过滤） |
| GET | `/api/eiu/{eiu_id}` | 单个 EIU 详情（含原文上下文） |
| PUT | `/api/eiu/{eiu_id}` | 手动编辑 EIU |
| DELETE | `/api/eiu/{eiu_id}` | 删除 EIU（标记为 excluded） |
| GET | `/api/corpus/{corpus_id}/eiu/coverage` | 覆盖率报告 |
| GET | `/api/corpus/{corpus_id}/eiu/gaps` | 未覆盖 EIU 清单 |

---

## 5. Demo 实现清单

- [x] LLM 客户端封装（OpenAI 兼容 API，`services/llm_client.py`，含重试 / JSON 修复 / 离线降级）
- [x] EIU 抽取 Prompt 模板（`prompts/eiu_extraction.txt`，含 P0/P1/P2 校准）
- [x] EIU 抽取器：逐 Block 调用 LLM，解析 JSON 输出（`services/eiu_extractor.py`）
- [x] `eiu` 表 + CRUD API（`EiuRow` 追加到 shared/database.py）
- [x] 覆盖清单 API：按文档/章节/类型/优先级分组统计（`services/coverage.py`）
- [x] 加权覆盖率计算（确定性代码，`covered_eiu_ids` 留给 M03 传入）
- [x] 实质 Block 对账检查（+ 覆盖率失真告警）
- [x] EIU 手动编辑/删除 API（软删除标记 blocked）
- [x] 文档更新自动重抽 EIU（覆盖式全量重算，复用 doc_update_job 进度）

### 配置与验收

- LLM 配置：`modules/shared/core/config.py` 追加 `LLM_API_BASE/KEY/MODEL/TEMPERATURE/MAX_TOKENS`；根目录 `.env`（gitignore 忽略）经 `python-dotenv` 自动加载。`LLM_API_KEY` 为占位符 `sk-xxx` 或缺少 openai 库时自动降级为离线确定性抽取。
- 真实模型验收：`python tests/acceptance_m02.py`（读取 `demo/.env` 的 DeepSeek 配置，覆盖 F1–F11 / D1–D6 / I1–I4，29 项全部通过）。
