# M02 — EIU 抽取与覆盖规划 · 开发 Spec

> 版本: v0.1 | 日期: 2026-08-03 | 依赖: M01 数据基础（已完成）

---

## 1. 目标

从 M01 产出的文档 Block 中，通过 LLM 逐块抽取可评测信息单元（EIU），生成覆盖清单与加权覆盖率报告。

**一句话**: 把 Block → 变成结构化的 EIU 表 + 覆盖统计数据。

---

## 2. 输入与输出

```
输入 (来自 M01):
  ├── document_block 表（block_id, document_id, section_path, block_text, block_type, parent_block_id）
  ├── document 表（document_id, file_name, corpus_id）
  ├── corpus 表（corpus_id, name）
  └── DatabaseService（复用 M01 的 DB 访问层）

输出 (M02 产出):
  ├── eiu 表（每条 EIU 绑定源 block_id）
  ├── 覆盖率报告 API（加权覆盖率 + 多维统计）
  ├── EIU CRUD API（列表/详情/编辑/删除）
  └── doc_update_job 进度（复用 M01 的 Job 机制）
```

---

## 3. 文件结构

```
modules/m02_eiu_coverage/
├── __init__.py
├── README.md              # 已有（技术方案文档）
├── SPEC.md                # 本文件
├── models.py              # EIU 数据类 (dataclass)
├── schemas.py             # Pydantic 请求/响应模型
├── api.py                 # FastAPI Router
├── prompts/
│   └── eiu_extraction.txt # LLM Prompt 模板
└── services/
    ├── __init__.py
    ├── llm_client.py      # LLM 客户端（OpenAI 兼容 API）
    ├── eiu_extractor.py   # EIU 抽取核心逻辑
    └── coverage.py        # 覆盖率计算（确定性代码）

modules/shared/core/
└── config.py              # 追加 LLM 相关配置项
```

---

## 4. 数据模型

### 4.1 eiu 表 (MySQL ORM)

| 字段 | 类型 | 说明 |
|---|---|---|
| eiu_id | INT PK AUTO | 主键 |
| corpus_id | INT FK | 所属语料库 |
| block_id | INT FK | 源 Block |
| statement | TEXT | EIU 完整陈述（一句话） |
| eiu_type | VARCHAR(32) | 10 种类型之一 |
| content_priority | VARCHAR(4) | P0 / P1 / P2 |
| weight | INT | 5 / 3 / 1 |
| constraints_json | JSON | {主体, 条件, 范围, 期间, 币种, 单位} |
| evidence_blocks | JSON | [block_id, ...] 引用的证据块 |
| is_questionable | BOOL | 是否可出题 |
| exclusion_reason | VARCHAR(128) | 不可出题原因（is_questionable=false 时填写） |
| extraction_model | VARCHAR(64) | LLM 模型名+版本 |
| extraction_confidence | FLOAT | 0.0–1.0 |
| review_status | VARCHAR(32) | candidate / quality_verified / blocked |
| created_at | DATETIME | 创建时间 |

### 4.2 10 种 EIU 类型

| 值 | 含义 | 题目方向 |
|---|---|---|
| `definition` | 定义 | 定义题 |
| `rule` | 规则 | 条件与适用范围题 |
| `threshold` | 阈值 | 阈值和数值题 |
| `date` | 日期 | 时效题 |
| `formula` | 公式 | 公式与计算题 |
| `process` | 流程 | 流程顺序题 |
| `exception` | 例外 | 例外与边界题 |
| `prohibition` | 禁止 | 是否可回答题 |
| `metric` | 指标 | 事实提取题 |
| `change` | 变更 | 比较与区分题 |

### 4.3 优先级与权重

| 优先级 | 权重 | 判定标准 |
|---|---|---|
| P0 | 5 | 监管禁止、关键阈值、例外条款、安全边界 |
| P1 | 3 | 核心定义、主流程、核心指标和公式 |
| P2 | 1 | 一般说明和补充事实 |

---

## 5. LLM 集成方案

### 5.1 配置项 (追加到 `modules/shared/core/config.py`)

```python
llm_api_base: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
llm_api_key: str = os.getenv("LLM_API_KEY", "sk-xxx")
llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))  # 抽取任务需低温
llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))
```

### 5.2 LLM 客户端 (`services/llm_client.py`)

```python
class LLMClient:
    """OpenAI 兼容 API 封装。"""
    def chat(self, messages: list[dict], response_format: dict | None = None) -> str:
        """发送聊天请求，返回文本响应。"""
    def extract_json(self, system_prompt: str, user_prompt: str) -> list[dict]:
        """发送 EIU 抽取请求，解析并返回 JSON 数组。"""
```

- 使用 `openai` 库
- 支持 response_format: `{"type": "json_object"}` 强制 JSON 输出
- 重试机制：网络错误重试 2 次，间隔 3s
- 超时 120s

### 5.3 EIU 抽取 Prompt 设计

**System Prompt** (`prompts/eiu_extraction.txt`):

```
你是一位精通银行授信政策和金融监管文件的专家。
你的任务是从给定的文档段落中抽取"可评测信息单元"（Evaluable Information Unit, EIU）。

## EIU 定义
一条 EIU 是能够被原文独立证明或否定、并能形成明确问题与答案的最小业务陈述。

## 8 条拆分规则
1. 独立真值：两项可分别判断真伪 → 拆为两个 EIU
2. 限定语不可脱离：主体/条件/范围/期间/币种/单位必须与结论在同一 EIU 中
3. 例外单列：一般规则与例外规则分别计数
4. 定义公式分列：定义/公式/变量口径/示例数值分别计数
5. 表格业务行：以"指标+主体+期间+单位+数值"完整记录为一个 EIU
6. 无实质不计数：标题/目录/过渡句/页眉页脚/重复免责声明 → 跳过
7. 重复合并：同一事实多处出现 → 分母只保留一条
8. 不可回答排除：证据残缺/无法确认 → 标记不可出题

## 10 种 EIU 类型
- definition: "X是指……""X包括……"
- rule: "……应当……""……不得……"
- threshold: 数值、百分比、上下限
- date: 生效/失效/过渡日期
- formula: 计算方式、变量关系
- process: 步骤序列
- exception: "除非……""……除外""……可以放宽"
- prohibition: "禁止……""不得……""严禁……"
- metric: 带主体/期间/币种/单位的指标值
- change: 版本对比、新旧更替

## 优先级判定
- P0：监管禁止事项、关键阈值、例外条款、安全边界
- P1：核心定义、主流程、核心指标和公式
- P2：一般说明和补充事实

## 输出格式
返回 JSON 数组。每个 EIU 包含:
{
  "statement": "完整陈述（一句话，可独立判定真伪）",
  "eiu_type": "rule|threshold|definition|date|formula|process|exception|prohibition|metric|change",
  "content_priority": "P0|P1|P2",
  "constraints": {
    "主体": "小微企业",
    "条件": "申请流动资金贷款时",
    "范围": null,
    "期间": null,
    "币种": null,
    "单位": null
  },
  "is_questionable": true|false,
  "exclusion_reason": "不可出题原因（is_questionable=false 时必须填写）"
}
```

**User Prompt 模板** (运行时拼接):

```
## 文档信息
- 文档名: {document_name}
- 章节路径: {section_path}

## 上文（前一个 Block）
{previous_block_text}

## 当前段落
{current_block_text}

## 下文（后一个 Block）
{next_block_text}

请抽取当前段落中的 EIU。如果段落无实质内容，返回空数组 []。
```

### 5.4 EIU 抽取流程

```
对每个段落 Block（跳过 block_type='title'）：
  1. skip_filter(block) → 纯标题/过渡句等直接跳过
  2. get_context(block) → 取前1后1 Block 作为上下文
  3. llm.extract_json(prompt) → 调 LLM 拿到 JSON 数组
  4. validate_eiu(items) → 校验每条 EIU 字段完整性
  5. 写入 eiu 表 → 绑定 corpus_id + block_id
  6. 更新 job.progress = 已处理 Block 数 / 总段落 Block 数
```

---

## 6. 覆盖规划（确定性代码，不依赖 LLM）

### 6.1 加权覆盖率公式

```
WeightedCoverage = Σ(w_i × c_i) / Σ(w_i)

其中:
  w_i: P0=5, P1=3, P2=1
  c_i: 1（已有通过质量校验的题目），0（未覆盖）
  分母: 仅含 is_questionable=true 的 EIU
```

### 6.2 覆盖率失真防护（代码规则）

| 失真类型 | 检测 | 实现阶段 |
|---|---|---|
| EIU 排除原因不合理 | rejection_reason 不能是"题目难生成" | M02 |
| 分母被人为排空 | 检查 excluded EIU 比例 > 50% 则告警 | M02 |
| 只有问题没有答案 | 检查 case.gold_answer 非空 | M04（不阻塞 M02） |
| 答案来自常识非原文 | LLM 忠实性检查 | M04（不阻塞 M02） |

### 6.3 业务门禁

- 总体加权覆盖率 ≥ 85% → 允许发布
- P0 EIU 覆盖率 = 100%（硬性）→ 否则阻断
- 实质 Block 对账率 = 100%（每个 Block 都要有 EIU 或 exclusion_reason）

### 6.4 Block 对账逻辑

```python
def check_block_reconciliation(corpus_id):
    """每个段落 Block 都必须有 EIU 或排除记录。"""
    all_blocks = db.list_blocks(corpus_id)  # 只统计 paragraph 类型
    eiu_covered_block_ids = {e.block_id for e in eius}
    
    uncovered = []
    for block in all_blocks:
        if block.block_type != 'paragraph':
            continue
        if block.block_id not in eiu_covered_block_ids:
            uncovered.append(block)
    
    return {
        'total_paragraph_blocks': len(all_blocks),
        'covered_blocks': len(eiu_covered_block_ids),
        'uncovered_blocks': uncovered,
        'reconciliation_rate': len(eiu_covered_block_ids) / len(all_blocks)
    }
```

---

## 7. API 设计

### 7.1 路由前缀: `/api/corpus/{corpus_id}`

| 方法 | 路径 | 说明 | 是否异步 |
|---|---|---|---|
| POST | `/eiu/extract` | 触发 EIU 抽取 | ✅ 异步 (返回 job_id) |
| GET | `/eiu` | EIU 清单 (支持 ?type=&priority=&questionable=&section=) | ❌ |
| GET | `/eiu/coverage` | 覆盖率报告 | ❌ |
| GET | `/eiu/gaps` | 未覆盖 EIU 清单 | ❌ |

### 7.2 全局路由（不绑定语料库）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/eiu/{eiu_id}` | EIU 详情（含原文上下文） |
| PUT | `/api/eiu/{eiu_id}` | 手动编辑 EIU |
| DELETE | `/api/eiu/{eiu_id}` | 删除 EIU（标记 blocked） |

### 7.3 请求/响应示例

**POST `/api/corpus/1/eiu/extract`**
```json
// Response 202
{
  "job_id": 2,
  "corpus_id": 1,
  "status": "running",
  "message": "开始 EIU 抽取，共 28 个段落 Block"
}
```

**GET `/api/corpus/1/eiu?priority=P0&type=rule`**
```json
// Response 200
{
  "corpus_id": 1,
  "total": 12,
  "items": [
    {
      "eiu_id": 1,
      "block_id": 14,
      "section_path": "第二章 业务要求 / 第五条 单位定期存单受理范围",
      "statement": "仅接受我行开具的单位定期存单质押，不接受他行开立的单位定期存单质押",
      "eiu_type": "rule",
      "content_priority": "P0",
      "weight": 5,
      "is_questionable": true,
      "review_status": "candidate",
      "created_at": "2026-08-03T10:00:00"
    }
  ]
}
```

**GET `/api/corpus/1/eiu/coverage`**
```json
{
  "corpus_id": 1,
  "total_eiu": 45,
  "questionable_eiu": 40,
  "excluded_eiu": 5,
  "by_priority": {"P0": 15, "P1": 20, "P2": 10},
  "by_type": {"rule": 12, "threshold": 8, "definition": 6, "prohibition": 5, "date": 4, "exception": 3, "process": 3, "metric": 2, "formula": 1, "change": 1},
  "by_document": [
    {"document_id": 1, "document_name": "附件1：…操作规程（2025年版）.docx", "eiu_count": 45}
  ],
  "by_section": [
    {"section_path": "第二章 业务要求", "eiu_count": 18},
    {"section_path": "第三章 业务操作流程", "eiu_count": 15}
  ],
  "weighted_coverage": 0.0,  // M03 生成题目后才会有值
  "p0_coverage_pct": 0.0,
  "block_reconciliation": {
    "total_paragraph_blocks": 28,
    "covered_blocks": 28,
    "rate": 1.0
  }
}
```

**PUT `/api/eiu/1`**
```json
// Request
{
  "statement": "修改后的陈述",
  "content_priority": "P0",
  "eiu_type": "rule"
}
// Response 200: 更新后的 EIU 对象
```

---

## 8. Job 进度机制（复用 M01）

EIU 抽取走异步 job，复用 M01 的 `doc_update_job`:

```
POST /api/corpus/{corpus_id}/eiu/extract
  → 创建 job (job_type="eiu_extract", status="pending")
  → 后台线程逐 Block 调 LLM
  → progress = 已处理 Block 数 / 总段落 Block 数 × 100
  → 每处理完一个 Block: 更新 progress + message
  → 全部完成: status="completed", message="EIU 抽取完成，共 N 条"
  → 失败: status="failed", message=错误详情
```

---

## 9. 验收标准

### 9.1 功能验收

| # | 测试项 | 验收标准 |
|---|---|---|
| F1 | EIU 抽取触发 | POST `/api/corpus/1/eiu/extract` 返回 job_id，后台开始处理 |
| F2 | Job 进度可查 | GET `/api/jobs/{id}` 返回 progress/phases/message |
| F3 | EIU 列表查询 | GET `/api/corpus/1/eiu` 返回所有 EIU，支持 ?priority=P0 过滤 |
| F4 | EIU 类型过滤 | GET `/api/corpus/1/eiu?type=rule&type=threshold` 返回复合过滤结果 |
| F5 | EIU 详情 | GET `/api/eiu/{id}` 含 statement/type/priority/原文上下文 |
| F6 | 手动编辑 | PUT `/api/eiu/{id}` 更新成功，字段校验 |
| F7 | 删除标记 | DELETE `/api/eiu/{id}` → review_status=blocked，不物理删除 |
| F8 | 覆盖率报告 | GET `/api/corpus/1/eiu/coverage` 含 all 6 个统计维度 |
| F9 | 未覆盖清单 | GET `/api/corpus/1/eiu/gaps` 返回 uncovered EIU 列表 |
| F10 | Block 对账 | coverage 报告中 reconciliation_rate 正确计算 |
| F11 | 空语料库处理 | 无 Block 时抽取返回提示"无可处理的段落"，不报错 |
| F12 | LLM 重试 | 网络错误自动重试 2 次，3 次全失败则该 Block 跳过并记录 |
| F13 | JSON 解析容错 | LLM 返回非标准 JSON 时尝试修复（截取 ```json...``` 块），失败则跳过 |

### 9.2 数据质量验收（用测试文档跑）

| # | 验收标准 | 预期 |
|---|---|---|
| D1 | EIU 总数 ≥ Block 数 × 0.3 | 每个段落平均产出 ≥ 1 条 EIU（排除纯标题后） |
| D2 | P0 EIU 占比 10%–40% | 不应该全部 P0 也不应该 0 条 P0 |
| D3 | EIU 类型分布 ≥ 5 种 | 银行规程文档至少含 rule/threshold/definition/date/prohibition |
| D4 | 每条 EIU 的 statement ≤ 200 字 | 不该有超长陈述 |
| D5 | is_questionable=false 必须有 exclusion_reason | 排除项可追溯 |
| D6 | 无重复 EIU（同一 block_id + statement 完全相同） | 去重 |

### 9.3 集成验收

| # | 验收标准 |
|---|---|
| I1 | 后端启动无报错，M02 router 正常注册 |
| I2 | `/health` 返回 OK |
| I3 | M01 上传的文档可正常触发 M02 抽取 |
| I4 | M02 不修改 M01 任何表结构和代码 |

---

## 10. 实现顺序

```
Phase 1: 基础设施 (2-3h)
  ├── models.py + eiu 表 ORM 追加到 DatabaseService
  ├── schemas.py (请求/响应 Pydantic 模型)
  ├── config.py 追加 LLM 配置项
  └── llm_client.py (OpenAI 兼容封装)

Phase 2: 核心抽取 (3-4h)
  ├── prompts/eiu_extraction.txt (Prompt 模板)
  ├── eiu_extractor.py (逐 Block 调 LLM + 解析)
  └── api.py (POST extract + GET list/detail + PUT + DELETE)

Phase 3: 覆盖规划 (1-2h)
  ├── coverage.py (加权覆盖率 + Block 对账)
  └── api.py (GET coverage + GET gaps)

Phase 4: 集成测试 (1-2h)
  ├── 用已上传的"存单质押操作规程.docx"跑完整链路
  ├── 数据质量检查
  └── 容错测试 (LLM 超时/返回异常 JSON)
```

---

## 11. 风险与约束

| 风险 | 缓解措施 |
|---|---|
| LLM API 不可用 | LLM 客户端内置重试，失败 Block 跳过不阻断 |
| LLM 返回非标准 JSON | 正则提取 ` ```json ... ``` ` 块，解析失败跳过 |
| Prompt 质量不稳定 | 先用测试文档跑 3 轮，人工抽查 20 条 EIU 后调 prompt |
| 进度不准确 | 只用 title-filter 后剩余的数量做分母 |
| 开放式 LLM 配置 | 兼容所有 OpenAI 兼容 API（千问/DeepSeek/vLLM） |

---

## 12. M01 代码对接清单

M02 需要 import 的 M01/Shared 模块：

| 模块 | 用途 |
|---|---|
| `modules.shared.services.database.DatabaseService` | 读写 document_block、创建 eiu 表 |
| `modules.shared.services.database.SessionLocal` | 数据库会话 |
| `modules.shared.core.config.settings` | 读 LLM 配置 |
| `modules.m01_data_foundation.services.pipeline.PipelineService` | 查询文档/Block（也可直接用 DatabaseService） |
