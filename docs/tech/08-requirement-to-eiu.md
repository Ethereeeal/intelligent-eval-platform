# 08 — 业务需求书→测试功能点

> 覆盖 BRD：8.20 业务需求书→测试功能点评测集生成
> Demo 状态：必做（EIU 提取，不含标准答案）

---

## 1. BRD 需求摘要

| 需求编号 | 需求 |
|---|---|
| FR-REQ2EIU-001 | 支持 PDF/DOCX/MD/TXT/XLSX 格式的业务需求书 |
| FR-REQ2EIU-002 | 需求书元数据：名称/版本/作者部门/业务领域/生效日期/评审日期 |
| FR-REQ2EIU-003 | 需求书解析与结构化：目录/章节/需求编号/功能名称/功能描述/业务规则/前后置条件/异常流程 |
| FR-REQ2EIU-004 | EIU 提取规则（6条扩展）：功能点/业务规则/数据规则/接口规则/非功能需求/排除规则 |
| FR-REQ2EIU-005 | **不生成标准答案**：仅产出 EIU 清单，每个 EIU 标记为 test_function_point 类型 |
| FR-REQ2EIU-006 | 测试功能点输出结构：eiu_id/需求文档ID/章节路径/需求编号/陈述/类型/优先级/证据范围/置信度 |
| FR-REQ2EIU-007 | 覆盖统计：按章节/模块/类型/优先级分组，P0 需求项不得遗漏 |
| FR-REQ2EIU-008 | 导出：JSON/JSONL/Excel/Markdown，预留测试管理平台字段映射 |

---

## 2. 与"文档→问答评测集"模式的区别

| 维度 | 业务需求书→测试功能点 | 文档→问答评测集 |
|---|---|---|
| **输入** | 业务需求规格说明书 | 授信政策、财报等专业文档 |
| **核心产出** | EIU 清单（测试功能点） | EIU + 标准答案 + 完整评测样本 |
| **是否生成答案** | **否** | 是 |
| **EIU 类型侧重** | functional_rule / business_rule / data_rule / interface_rule / nfr | definition / rule / threshold / date / formula / process / exception / prohibition / metric / change |
| **覆盖衡量** | EIU 对账率、章节覆盖率 | 加权 EIU 覆盖率（>85%）、证据回溯率 |
| **可执行评测** | 否（需人工补答案后转为评测集） | 是 |
| **适用阶段** | 需求评审、测试设计 | 系统验收、回归测试 |

---

## 3. 技术方案

### 3.1 需求书解析

与"文档→问答评测集"的文档解析共用同一套解析模块：

```
需求书上传
  → 格式检测（PDF/DOCX/MD/TXT/XLSX）
  → 调用对应解析器
  → 抽取结构化字段：
      - 需求编号（正则匹配：FR-XXX-XXX / REQ-XXX / 自定义格式）
      - 功能名称（标题层级推断）
      - 功能描述
      - 业务规则
      - 前置条件 / 后置条件
      - 异常流程
  → 写入 requirement_doc 表 + Block 表
```

### 3.2 EIU 提取规则（FR-REQ2EIU-004，6条）

| # | 规则 | 检测方式 | 示例 |
|---|---|---|---|
| 1 | 功能点识别 | LLM：匹配"系统应/应支持/应提供/应实现……" | "系统应支持用户通过用户名+密码方式登录" → functional_rule |
| 2 | 业务规则识别 | LLM：匹配"如果…则…""当…时…""…不得…""…必须…" | "当用户连续5次输入错误密码时，账户应锁定30分钟" → business_rule |
| 3 | 数据规则识别 | LLM：字段定义/格式/取值范围/校验规则 | "用户名应为3-32位字母数字组合" → data_rule |
| 4 | 接口规则识别 | LLM：输入参数/输出格式/异常返回码定义 | "登录接口返回 {code, token, expire}" → interface_rule |
| 5 | 非功能需求识别 | LLM：性能指标/安全要求/可用性/SLA | "登录接口在99%请求下应在2秒内返回" → nfr |
| 6 | 排除规则 | LLM：纯背景描述/业务目标概述/非约束性建议 | "本项目旨在提升用户体验" → exclusion_reason |

### 3.3 提取流程

```
POST /api/requirements/{id}/extract
  → 获取需求书的 Block 列表
  → 对每个 Block 调用 LLM（使用需求书专用 EIU 提取 Prompt）
  → 解析 JSON 输出
  → 写入 test_function_point 表
  → 统计章节对账率
  → 返回提取结果摘要
```

### 3.4 数据模型

**requirement_doc 表：**

| 字段 | 类型 | 说明 |
|---|---|---|
| requirement_doc_id | INT PK | |
| corpus_id | INT FK | |
| file_name | VARCHAR | |
| file_type | VARCHAR | |
| requirement_version | VARCHAR | 需求文档版本号 |
| business_domain | VARCHAR | |
| author_department | VARCHAR | |
| effective_date | DATE | |
| review_date | DATE | |
| parse_status | VARCHAR | |
| uploaded_at | DATETIME | |

**test_function_point 表：**

| 字段 | 类型 | 说明 |
|---|---|---|
| tfp_id | INT PK | |
| requirement_doc_id | INT FK | |
| section_path | VARCHAR | |
| requirement_id | VARCHAR | 原始需求编号 |
| statement | TEXT | 功能点完整陈述 |
| eiu_type | VARCHAR | functional_rule / business_rule / data_rule / interface_rule / nfr |
| content_priority | VARCHAR | P0 / P1 / P2 |
| weight | INT | |
| evidence_range | JSON | 原文定位 |
| is_questionable | BOOL | |
| exclusion_reason | VARCHAR | |
| extraction_confidence | FLOAT | |
| review_status | VARCHAR | |
| created_at | DATETIME | |

---

## 4. 覆盖统计（FR-REQ2EIU-007）

区别于问答评测集的加权覆盖率公式，需求书模式使用**章节对账率**：

```
章节对账率 = 有至少一个 EIU 或排除记录的实质章节数 / 总实质章节数

门禁：
  - 每个有实质内容的需求章节必须至少关联 1 个 EIU 或排除记录
  - P0 需求项（安全/合规相关需求）不得有 EIU 遗漏
  - 所有 EIU 必须通过治理审核 Skill 的安全合规检查
```

---

## 5. 导出（FR-REQ2EIU-008）

| 格式 | 结构 | 用途 |
|---|---|---|
| JSON | 完整 test_function_point 对象数组 | 导入测试管理工具 |
| JSONL | 每行一个 TFP | 流式处理 |
| Excel | 扁平表格 + 优先级着色 | 人工审阅 |
| Markdown | 按需求书原目录结构组织 | 文档化交付 |

---

## 6. API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/requirements/upload` | 上传业务需求书 |
| GET | `/api/requirements` | 需求书列表 |
| GET | `/api/requirements/{id}` | 需求书详情 |
| POST | `/api/requirements/{id}/extract` | 触发 EIU 提取 |
| GET | `/api/requirements/{id}/test-function-points` | 查看测试功能点（支持过滤） |
| GET | `/api/requirements/{id}/export?format=json` | 导出测试功能点 |

---

## 7. Demo 实现清单

- [ ] `requirement_doc` 表 + 上传 API
- [ ] 需求书专用 EIU 提取 Prompt（6 条规则，Few-shot 示例）
- [ ] 需求书 EIU 提取器（复用 EIU 抽取管道，差异在 Prompt 和后处理）
- [ ] `test_function_point` 表 + CRUD API
- [ ] 章节对账率计算
- [ ] JSON / Excel 导出
- [ ] （延后）XLSX 需求矩阵的列映射
- [ ] （延后）测试管理平台字段映射
