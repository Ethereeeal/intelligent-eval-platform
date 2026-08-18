# 01 — 数据基础：语料库、文档接入、解析、存储与索引

> 覆盖 BRD：8.1 语料库与文档接入 / 8.2 结构化解析与可回溯定位 / 8.4 存储与索引
> Demo 状态：必做

---

## 1. BRD 需求摘要

### 8.1 语料库与文档接入

| 需求编号 | 需求 |
|---|---|
| FR-CORPUS-001 | 创建隔离的语料库（当前实现按「文档库 + 文件夹」组织，无 corpus 表，见 §2.1） |
| FR-CORPUS-002 | 文件接入支持 PDF/DOCX/TXT/MD/CSV/XLSX；保存文件名/哈希/版本/权威等级 |
| FR-CORPUS-004 | 文档更新（content_hash 变化）自动触发重新解析与 EIU 重抽，并显示更新进度，完成后提示"已更新完成"（已实现，见 §2.8） |
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
| FR-STORAGE-001 | 五层后台存储：原始文件/关系型数据/向量索引/语义理解/配置与版本；EIU 为向量化核心对象（BRD V1.3 §5.7，chunk/Block 为中间结构、主要服务检索） |
| FR-INDEX-001 | 多路索引：关键词稀疏/稠密向量（仅 EIU 向量，Block 已不再向量化）/元数据/结构关系/表格 |
| FR-INDEX-002 | FAISS 适用边界：原型或单机高效近邻检索，不承担业务数据库职责 |
| FR-INDEX-003 | 覆盖式重处理：重传文档整体重新分段+向量化（Demo 不做增量，见 §2.8） |
| FR-INDEX-004 | Embedding/Reranker 预配置：模型名称/版本/维度/批大小/归一化方式/健康检查 |

---

## 2. 技术实现方案

### 2.1 文档库与文件夹管理

> 说明：当前实现按「文档库 + 文件夹」维度组织（`folder` 表 + `document.folder_path`），**无 corpus 表 / corpus 接口**；BRD 的语料库概念尚未启用。

```
GET    /api/folders             → 全部文件夹（含空文件夹），前端据此重建目录树
POST   /api/folders             → 创建文件夹（owner + name + parent_path，同父下禁止重名）
PATCH  /api/folders/move        → 移动/重命名文件夹（from_path → to_path，联动重写文档/问答对 folder_path）
DELETE /api/folders?path=...    → 删除文件夹（递归子孙；其下文档上移父目录，问答对一并物理删除）
```

**数据模型（folder 表）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| folder_id | INT PK | |
| name | VARCHAR(255) | 文件夹名（同父下唯一） |
| parent_id | INT | 父文件夹 ID，NULL = 文档库根 |
| owner | VARCHAR(128) | 归属（当前单用户，仅记录，不按 owner 隔离） |
| created_at | DATETIME | |

文档通过 `document.folder_path`（相对文档库根的子路径，如「子A/子B」，空串 = 根）与文件夹关联。

### 2.2 文档上传与存储

```
POST /api/documents/upload
  → multipart/form-data: folder_path + purpose + upload_user + file
  → 计算 SHA256 → 查重 → 存本地 → 写入 document 表 → 触发解析 → 返回 document_id

POST /api/documents/precheck（只读预检，混合上传用）
  → 返回 ok（可直接上传）/ duplicate（内容已存在，跳过）/ conflict（同名覆盖，签发 confirm_token）/
    ok + same_name_elsewhere（其他位置同名，弱提示）
```

**文件存储路径：** `storage/raw/{uuid12}_{original_filename}`（容器内 `/app/storage/raw`，docker 卷 `backend_storage` 持久化；`minio_path` 字段暂存本地绝对路径，MinIO 未接线）

**数据模型（document 表）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| document_id | INT PK | |
| file_name | VARCHAR(255) | |
| file_type | VARCHAR(64) | PDF/DOCX/TXT/MD/CSV/XLSX |
| file_size | BIGINT | |
| file_hash | VARCHAR(128) | SHA256，UNIQUE，去重（相同内容不重复解析） |
| minio_path | VARCHAR(512) | 本地文件绝对路径（MinIO 接入后改为对象 key） |
| upload_user | VARCHAR(128) | |
| document_version | VARCHAR(64) | 覆盖式：文档不版本化，恒为单一版本（预留字段） |
| authority_level | VARCHAR(32) | 权威等级 |
| folder_path | VARCHAR(512) | 相对文档库根的子路径，空 = 根 |
| purpose | VARCHAR(16) | 业务用途标记（basic / gen） |
| parse_status | VARCHAR(64) | pending / parsing / done / failed |
| parse_error | TEXT | 解析失败原因 |
| status | VARCHAR(64) | 当前状态（uploaded 等） |
| created_at | DATETIME | 上传时间 |

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

### 2.4 Block 存储与 EIU 向量化

> **P0 改造（BRD V1.3 §5.7）**：向量化核心对象从 Block（chunk）改为 **EIU**。Block 仍承担结构存储与原文定位（FR-PARSE-003），chunk/Block 是文档切分的中间结构、主要服务检索；EIU 承载完整语义，是向量化与跨文档知识融合的基础。实现：`modules/m01_data_foundation/services/eiu_indexer.py`（`EiuFaissIndex`）。

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

**向量化（仅 EIU）：**

```
EIU 陈述 → BGE-small-zh-v1.5（512 维，已归一化）→ FAISS IndexFlatIP（余弦等价）
                                            └── 记录 eiu_id ↔ vector_id 映射
```

> **Block 向量已废弃**：`pipeline.embed_blocks` 统一把 `embedding_vector` 置 `None`，Block 仅作为"定位分片"承载原文（FR-PARSE-003），不再做向量化；文档检索当前为关键词打分（`services/retrieval.py`，未接入主链路），`services/indexer.py`（FaissIndexService）为预留死代码。

**EIU 向量的用途：**
1. EIU 抽取时语义去重（m02，已实现）
2. 跨段/跨文档关系发现时，EIU 相似度聚类 + Top-K 近邻作为候选（BRD V1.3 §8.7，后续版本）
3. 证据扩展时，检索邻接段落补充上下文（未来可回补 Block 向量，当前未实现）

**Demo 阶段：** EIU 向量化已实现（`eiu.embedding_vector` 落库 + `EiuFaissIndex` 进程内索引）；FAISS 不可用或无向量时优雅降级，不阻断主链路。

### 2.5 BGE 模型加载（本地挂载，需手动下载）

> **重要**：BGE 模型 **不在构建期下载、也不在运行期联网下载**，而是由宿主机根目录 `models/` 挂载进容器后 **本地加载**（运行期零联网依赖）。下载方式与目录结构见仓库根目录 `models/README.md`。

- 向量化 / 语义分段模型：`BAAI/bge-small-zh-v1.5`
  - 加载代码：`modules/m01_data_foundation/services/embedding.py`
  - 优先路径：`$LOCAL_MODELS_DIR/bge-small-zh-v1.5`（默认 `/app/models/bge-small-zh-v1.5`，即宿主机 `intelligent-eval-platform/models/bge-small-zh-v1.5`）
  - 本地目录不存在时回退到 HuggingFace Hub 在线下载
- 重排模型：`BAAI/bge-reranker-v2-m3`（CrossEncoder）
  - 加载代码：`modules/shared/services/rerank.py`
  - 优先路径：`$LOCAL_MODELS_DIR/bge-reranker-v2-m3`

### 2.6 存储体系（当前实现）

| 存储层 | 当前实现 | 说明 |
|---|---|---|
| 原始文件 | 本地 `storage/raw/`（容器内 `/app/storage/raw`，docker 卷 `backend_storage`） | MinIO 已部署未接线，`minio_path` 暂存本地绝对路径 |
| 关系型数据 | MySQL 8（docker `evalforge` 库，卷 `mysql_data`） | SQLAlchemy + pymysql；SQLite 仅作兼容（`DATABASE_URL` 可切换） |
| 向量索引 | 进程内 FAISS（`EiuFaissIndex`，从 MySQL 全量重建，不落盘） | EIU 向量 512 维 IndexFlatIP；Block 向量已废弃 |
| 语义理解 | MySQL（EIU 表及其他语义表） | 无独立语义存储 |
| 配置与版本 | `.env` + 环境变量 + 代码内 Prompt 模板 | 模型本地挂载 `./models` |

### 2.7 文档安全预处理（Demo 简化）

Demo 阶段不实现完整的 FR-CORPUS-003，仅做：
- 文件类型白名单校验（拒绝 .exe/.dll/.so 等可执行文件）
- 文件大小限制（≤ 50MB）
- 加密/损坏文件检测（PyMuPDF 打开失败时明确标记）

### 2.8 文档重传闭环（FR-CORPUS-004，已实现）

当某文档的 **content_hash 发生变化**（覆盖式重传），后端自动完成"重解析 → EIU 重抽 → 版本重建 → 删除旧文档"闭环，并向前端暴露统一进度：

**触发方式：**
- 上传预检（`POST /api/documents/precheck`）+ 混合确认：目标文件夹同名且内容不同 → 用户确认后带 `confirm_token` 调 `POST /api/documents/{document_id}/reupload`；
- 或直接显式调 reupload 接口（不传 token 也可，用于测试/接口调用）。

**闭环流程（m01 API 编排线程 `_run_reupload_chain`）：**

```
1. 新内容入库：存文件 + 解析 + 写块（保留原文档 folder_path / purpose / document_version；旧文档暂不删除）
2. EIU 重抽：m02 extract_document(finalize_job=False)，复用同一 doc_update_job
3. 版本覆盖重建：m05 rebuild_on_reupload → job done + "已更新完成"
4. 删除旧文档（块 / EIU / 问答对 / 落盘文件）
```

**失败策略：** 解析 / 抽取 / 重建任一环节失败 → 回滚新文档、保留旧文档、`job=failed`；全链路成功后的旧文档清理失败只标记 job，不回滚已生效的新文档。

**进度与状态（job 机制，统一单调递增）：**

| 阶段 | phase | progress |
|---|---|---|
| 排队/解析中 | `parsing` | 10 → 40 |
| EIU 抽取（按 Block 数推进） | `eiu_extract` | 40 → 90 |
| 版本重建 | `rebuild` | 90 → 100 |
| 完成/失败 | `done` / `failed` | 100 / 失败原因 |

- `status`：pending → running → done / failed（完成消息"已更新完成"）；
- 前端通过 `GET /api/jobs/{job_id}` 轮询进度与状态。

**doc_update_job 表：**

| 字段 | 类型 | 说明 |
|---|---|---|
| job_id | INT PK | |
| document_id | INT FK | 被更新的文档 |
| job_type | VARCHAR | doc_update / eiu_extract |
| status | VARCHAR | pending / running / done / failed |
| phase | VARCHAR | parsing / eiu_extract / rebuild / unchanged |
| progress | INT | 0–100（整体刻度，见上表） |
| message | VARCHAR | 阶段说明 / "已更新完成" / 失败原因 |
| created_at | DATETIME | |
| finished_at | DATETIME | |

---

## 3. API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/folders` | 文件夹列表（含空文件夹） |
| POST | `/api/folders` | 创建文件夹 |
| PATCH | `/api/folders/move` | 移动/重命名文件夹（联动重写文档/问答对 folder_path） |
| DELETE | `/api/folders?path=&owner=` | 删除文件夹（递归子孙，文档上移父目录，问答对物理删除） |
| POST | `/api/documents/precheck` | 上传预检（只读）：ok / duplicate / conflict（签发 confirm_token）/ 弱提示 |
| POST | `/api/documents/upload` | 上传文档，触发解析 |
| GET | `/api/documents` | 文档列表 |
| GET | `/api/documents/{document_id}` | 文档详情 |
| GET | `/api/documents/{document_id}/blocks` | Block 列表（含章节树） |
| PATCH | `/api/documents/{document_id}/move` | 移动文档到目标目录（重写 folder_path / purpose） |
| PATCH | `/api/documents/{document_id}/rename` | 重命名文档（仅显示名，不影响落盘文件与问答对） |
| POST | `/api/documents/{document_id}/reupload` | 上传同文档新版本（content_hash 变化则触发更新） |
| DELETE | `/api/documents/{document_id}` | 物理删除文档（块 + EIU + 问答对 + 落盘文件） |
| GET | `/api/jobs/{job_id}` | 查询更新/抽取任务进度与状态 |

---

## 4. Demo 实现清单

- [x] `folder` 表 + 文件夹 CRUD / 移动 / 删除 API（无 corpus，见 §2.1）
- [x] `document` 表 + 上传 API + 哈希去重 + 上传预检（precheck / confirm_token）
- [x] `block` 表 + 解析器（TXT/MD/PDF/DOCX/XLSX/CSV）
- [x] 层级文段构建（标题推断 + parent_block_id + section_path）
- [x] 解析状态管理 + 错误记录
- [x] EIU 向量化 + FAISS 索引（`EiuFaissIndex`，EIU 为核心向量化对象；Block 向量已废弃，仅作定位分片）
- [x] 文件类型白名单 + 大小限制
- [x] 文档重传闭环（content_hash 变化 → 覆盖式全量重算：重解析 + EIU 重抽 + 版本重建 + 删旧文档，无版本）
- [x] `doc_update_job` 进度状态机（parsing → eiu_extract → rebuild，进度统一单调）+ 进度查询 API
