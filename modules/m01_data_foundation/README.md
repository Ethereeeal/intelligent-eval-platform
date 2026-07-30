# 01 — 数据基础：语料库、文档接入、解析、存储与索引

> 覆盖 BRD：8.1 语料库与文档接入 / 8.2 结构化解析与可回溯定位 / 8.4 存储与索引
> Demo 状态：必做

---

## 1. BRD 需求摘要

### 8.1 语料库与文档接入

| 需求编号 | 需求 |
|---|---|
| FR-CORPUS-001 | 创建隔离的语料库，支持多文件归属，跨文档比对限于同一语料库 |
| FR-CORPUS-002 | 文件接入支持 PDF/DOCX/TXT/MD/CSV/XLSX；保存文件名/哈希/版本/权威等级 |
| FR-CORPUS-004 | 文档更新（content_hash 变化）自动触发重新解析与 EIU 重抽，并显示更新进度，完成后提示"已更新完成" |
| FR-CORPUS-003 | 文档安全预处理：病毒检测、敏感信息识别、提示注入识别、外发模型标记 |

### 8.2 结构化解析与可回溯定位

| 需求编号 | 需求 |
|---|---|
| FR-PARSE-001 | 版面感知解析：标题/目录/章节/页眉页脚/表格/图片/页码/版面坐标 |
| FR-PARSE-002 | 层级文段：文档→章节→小节→语义段落/表格→句子/表格行/原子证据 |
| FR-PARSE-003 | 原文定位：每个可检索文段含 document_id/version/section_path/page_no/block_id/偏移 |
| FR-PARSE-004 | 解析质量门禁：检测乱码/空页/目录错位/表格错列/OCR低置信度 |

### 8.4 存储与索引

| 需求编号 | 需求 |
|---|---|
| FR-STORAGE-001 | 五层后台存储：原始文件/关系型数据/向量索引/语义理解/配置与版本 |
| FR-INDEX-001 | 多路索引：关键词稀疏/稠密向量/元数据/结构关系/表格 |
| FR-INDEX-002 | FAISS 适用边界：原型或单机高效近邻检索，不承担业务数据库职责 |
| FR-INDEX-003 | 覆盖式重处理：重传文档整体重新分段+向量化（Demo 不做增量，见 §2.7） |
| FR-INDEX-004 | Embedding/Reranker 预配置：模型名称/版本/维度/批大小/归一化方式/健康检查 |

---

## 2. 技术实现方案

### 2.1 语料库管理

```
POST /api/corpus
  → 创建语料库记录（名称/领域/创建人/版本）

GET /api/corpus/{corpus_id}
  → 返回语料库详情 + 文档数 + EIU数 + 覆盖率摘要
```

**数据模型（corpus 表）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| corpus_id | INT PK | |
| name | VARCHAR(255) | 语料库名称 |
| description | TEXT | |
| domain | VARCHAR(128) | 授信政策 / 企业财报 / ... |
| created_by | VARCHAR(128) | |
| created_at | DATETIME | |
| version | VARCHAR(64) | 语料库版本号 |

### 2.2 文档上传与存储

```
POST /api/documents/upload
  → multipart/form-data: corpus_id + file
  → 计算 SHA256 → 查重 → 存本地 → 写入 document 表 → 触发解析 → 返回 document_id
```

**文件存储路径：** `storage/raw/{sha256}_{original_filename}`

**数据模型（document 表）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| document_id | INT PK | |
| corpus_id | INT FK | |
| file_name | VARCHAR(255) | |
| file_type | VARCHAR(64) | PDF/DOCX/TXT/MD/CSV/XLSX |
| file_size | BIGINT | |
| content_hash | VARCHAR(128) | SHA256，UNIQUE，去重（相同内容不重复解析） |
| storage_path | VARCHAR(512) | 本地文件路径 |
| upload_user | VARCHAR(128) | |
| upload_time | DATETIME | |
| document_version | VARCHAR(64) | Demo 覆盖式：文档不版本化，恒为单一版本（预留字段，可去除） |
| authority_level | VARCHAR(32) | 权威等级 |
| parse_status | VARCHAR(64) | pending / parsing / done / failed |
| parse_error | TEXT | 解析失败原因 |

### 2.3 文档解析

**解析器选择（按文件类型）：**

| 文件类型 | 解析库 | 提取内容 |
|---|---|---|
| TXT | 直接读取 | 段落 |
| MD | `markdown` + 正则 | 标题层级 + 段落 + 列表 + 代码块 |
| PDF | `PyMuPDF` (fitz) | 文本 + 页码 + 字体大小（推测标题） |
| DOCX | `python-docx` | 段落 + 表格 + 样式（推测标题层级） |
| XLSX | `openpyxl` | 工作表名 + 行列数据 |
| CSV | `csv` | 行数据 |

**层级文段构建（FR-PARSE-002）：**

```
解析输出结构：
{
  "block_id": 唯一标识,
  "parent_block_id": 父节点（标题→段落）,
  "section_path": "第三章 > 3.2 授信准入 > 3.2.1 基本条件",
  "page_no": 12,
  "block_type": "paragraph | table_row | title | list_item",
  "block_text": "原文文本...",
  "start_offset": 字符起始位置,
  "end_offset": 字符结束位置,
  "metadata_json": { "font": "...", "is_bold": false }
}
```

**标题层级推断（PDF/DOCX）：**
1. 通过字体大小、加粗、编号模式（"第X章""X.X""（X）"）推断标题
2. 构建父子关系：标题 Block 的 block_id 作为后续内容 Block 的 parent_block_id
3. 拼接 section_path：沿父节点链向上的标题文本拼接

**语义分段（基于 BGE 模型）：**
- 连续文本切分为语义完整的 Block 边界，由 BGE 语义分段模型判定，而非仅依赖版面结构或标点断句。
- 与版面解析互补：版面结构提供章节骨架（标题层级），BGE 语义分段在段落内部对齐语义边界，避免把一处完整语义拆散、或把若干不同语义强行合并为一个 Block。
- 同一 BGE 模型同时承担 §2.4 的向量化嵌入（FR-INDEX-004 预配置其名称/版本/维度）。

**解析质量门禁（FR-PARSE-004，Demo 简化）：**
- 检测空页：page_no 有但无对应 block → 标记
- 检测乱码：不可打印字符占比 > 阈值 → 标记
- Demo 阶段：发现问题时记入 parse_error，不阻断流程

### 2.4 Block 存储与向量化

**数据模型（block 表）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| block_id | INT PK | |
| document_id | INT FK | |
| parent_block_id | INT | 父节点 ID |
| section_path | VARCHAR(512) | |
| page_no | INT | |
| block_type | VARCHAR(64) | |
| block_text | TEXT | |
| start_offset | INT | |
| end_offset | INT | |
| metadata_json | JSON | |

**向量化（辅助用途，非核心路径）：**

```
Block 文本 → BGE-small-zh-v1.5 → 768维向量 → FAISS Index
                                            └── 记录 block_id ↔ vector_id 映射
```

**向量化的三个辅助场景：**
1. EIU 抽取时，检索相似 Block 帮助 LLM 判断是否重复
2. 跨段关系发现时，Top-K 近邻作为候选（后续版本）
3. 证据扩展时，检索邻接段落补充上下文

**Demo 阶段：** 向量化可先做简化版（仅用于 Block 去重提醒），不阻塞主链路。

### 2.8 BGE 模型加载（本地挂载，需手动下载）

> **重要**：BGE 模型 **不在构建期下载、也不在运行期联网下载**，而是由宿主机根目录 `models/` 挂载进容器后 **本地加载**（运行期零联网依赖）。下载方式与目录结构见仓库根目录 `models/README.md`。

- 向量化 / 语义分段模型：`BAAI/bge-small-zh-v1.5`
  - 加载代码：`modules/m01_data_foundation/services/embedding.py`
  - 优先路径：`$LOCAL_MODELS_DIR/bge-small-zh-v1.5`（默认 `/app/models/bge-small-zh-v1.5`，即宿主机 `intelligent-eval-platform/models/bge-small-zh-v1.5`）
  - 本地目录不存在时回退到 HuggingFace Hub 在线下载
- 重排模型：`BAAI/bge-reranker-v2-m3`（CrossEncoder）
  - 加载代码：`modules/shared/services/rerank.py`
  - 优先路径：`$LOCAL_MODELS_DIR/bge-reranker-v2-m3`

### 2.5 存储体系（Demo 简化）

| 存储层 | Demo 实现 | 生产迁移 |
|---|---|---|
| 原始文件 | 本地 `storage/raw/` | MinIO |
| 关系型数据 | SQLite `storage/qa_gen.db` | PostgreSQL |
| 向量索引 | FAISS 本地文件 `storage/faiss.index` | 向量数据库 |
| 语义理解 | SQLite（EIU 表及其他语义表） | PostgreSQL  |
| 配置与版本 | 环境变量 + 代码内 Prompt 模板 | 配置中心 |

### 2.6 文档安全预处理（Demo 简化）

Demo 阶段不实现完整的 FR-CORPUS-003，仅做：
- 文件类型白名单校验（拒绝 .exe/.dll/.so 等可执行文件）
- 文件大小限制（≤ 50MB）
- 加密/损坏文件检测（PyMuPDF 打开失败时明确标记）

### 2.7 文档更新自动重抽 EIU 与进度（FR-CORPUS-004）

当同一语料库内某文档的 **content_hash 发生变化**（用户重新上传该文档，覆盖旧版本），平台应自动完成"重解析 → 重抽 EIU → 覆盖重建"闭环，并向前端暴露进度：

**触发方式：**
- 复用上传入口：重新上传同名/同业务标识文档，`content_hash` 与既有记录不同 → 视为该文档的**覆盖更新**（不创建版本，旧文档整体作废）。
- 或显式 `POST /api/documents/{document_id}/reupload` 上传新版本。

**进度与状态（job 机制）：**
每次更新生成一个 `doc_update_job`，贯穿"解析 → EIU 抽取 → 覆盖重建"全链路：
- `status`：pending → running → done / failed
- `phase`：parsing（整体重解析）→ eiu_extract（全量重抽 EIU）→ rebuild（删除旧文档全部 block/向量/EIU/题目，写入新生成结果）
- `progress`：0–100，按已处理 Block 数 / 总 Block 数推进；完成置 100
- `message`：进行中显示当前阶段说明；**完成时显示"已更新完成"**；失败显示失败原因
- 前端通过 `GET /api/jobs/{job_id}` 轮询进度与状态，渲染进度条与"已更新完成"提示。

**doc_update_job 表：**

| 字段 | 类型 | 说明 |
|---|---|---|
| job_id | INT PK | |
| corpus_id | INT FK | |
| document_id | INT FK | 被更新的文档 |
| job_type | VARCHAR | upload / update / extract |
| status | VARCHAR | pending / running / done / failed |
| phase | VARCHAR | parsing / eiu_extract / rebuild |
| progress | INT | 0–100 |
| message | VARCHAR | 阶段说明 / "已更新完成" / 失败原因 |
| created_at | DATETIME | |
| finished_at | DATETIME | |

---

## 3. API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/corpus` | 创建语料库 |
| GET | `/api/corpus` | 语料库列表 |
| GET | `/api/corpus/{corpus_id}` | 语料库详情 |
| POST | `/api/documents/upload` | 上传文档，触发解析 |
| GET | `/api/documents` | 文档列表（支持 ?corpus_id= 过滤） |
| GET | `/api/documents/{document_id}` | 文档详情 |
| GET | `/api/documents/{document_id}/blocks` | Block 列表（含章节树） |
| POST | `/api/documents/{document_id}/reupload` | 上传同文档新版本（content_hash 变化则触发更新） |
| GET | `/api/jobs/{job_id}` | 查询更新/抽取任务进度与状态 |

---

## 4. Demo 实现清单

- [ ] `corpus` 表 + CRUD API
- [ ] `document` 表 + 上传 API + 哈希去重
- [ ] `block` 表 + 解析器（TXT/MD/PDF/DOCX）
- [ ] 层级文段构建（标题推断 + parent_block_id + section_path）
- [ ] 解析状态管理 + 错误记录
- [ ] BGE 向量化 + FAISS 索引（辅助）
- [ ] 文件类型白名单 + 大小限制
- [ ] 文档更新触发（content_hash 变化 → 覆盖式全量重算，无版本）
- [ ] `doc_update_job` 进度状态机 + 进度查询 API（前端显示进度，完成提示"已更新完成"）
