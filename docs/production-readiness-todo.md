# EvalForge 生产化前代办清单（2026-08）

> 目的：汇总生产化前必须处理的技术债、安全加固、业务口径确认与存储方案，作为唯一收口文档。
> 状态：A 节为**已完成**；B 节为**待办**（按优先级）；C 节为归档说明；D 节为保留文档索引。

---

## A. 已完成（2026-08 落地）

- **文档重传后端闭环**：`POST /api/documents/{id}/reupload` 全链路（重解析 → EIU 重抽 → 版本重建 → 删旧文档）；统一 `doc_update_job`（`parsing → eiu_extract → rebuild → done/failed`）；进度单调不回跳（10 / 40 / 40–90 / 90 / 100）；失败保留旧文档、回滚新文档；
- **混合上传**：后端 `POST /api/documents/precheck`（只读预检）+ `confirm_token`（一次性、10 分钟、绑定 document_id + 文件哈希）；前端预检限并发 3、异常确认面板（将覆盖 / 弱提示，可逐行移除）、覆盖确认后带 token 走 reupload、重传进度浮层；
- **上传内存炸弹修复**：precheck / upload / reupload 三个入口改为流式限长读取（1MB 分块，超限返回 413）；
- **其他修复**：重复上传不再残留孤儿文件（查重通过后落盘）；confirm_token 过期清理；编排失败按实际阶段记录；reupload 未预期异常收敛为 500；前端 `fmtSize` 全局函数名冲突修复；
- **CLAUDE.md 单源化**：改为 `@AGENTS.md` 导入入口，开发流程规范只维护一份，避免双份漂移；
- **README 全面对齐**：m01/m02/m03/m04/m05 与根 README、docs/data-model.md（corpus 概念移除、Block 向量废弃、MySQL 存储体系、实际 API 路由、重传闭环描述）。
- **P0 安全加固（2026-08-18）**：
  - **认证与访问控制**：`API_TOKEN` 可开关鉴权（`Authorization: Bearer` / `X-API-Token`，常量时间比较，默认关闭保持 Demo 联调）；CORS 从 `*` 收紧为白名单（默认 localhost:8080，`CORS_ORIGINS` 可配）；文档删除 / 文件夹删除 / 覆盖重传写入 `audit_log` 审计表；
  - **压缩炸弹防护**：PDF 页数、表格行数 / 单元格数、DOCX 元素数解析前上限（`MAX_PDF_PAGES` / `MAX_TABLE_ROWS` / `MAX_XLSX_CELLS` / `MAX_DOCX_BLOCKS`，env 可配）；
  - **`delete_folder` LIKE 通配符误删**：改为 `startswith(autoescape=True)`，文件夹名含 `%` / `_` 不再误匹配其他目录；
  - **上传并发唯一约束兜底**：同哈希并发上传捕获 `IntegrityError`，清理本请求已落盘文件并按重复返回；
  - **删除接口异常收敛**：不再向客户端回显内部异常，详情进日志。

---

## B. 生产化前待办

### P1（生产化阶段）

1. **运行时联调测试**（需 MySQL / 后端服务）：正常上传、重复上传、同名覆盖确认（token）、重传闭环各 job 阶段与失败回滚；前端确认面板全流程（实现已落地，待联调验证）；
2. **同文档并发重传加锁**：按 document 互斥，避免产生多个新文档或重复删除；
3. **数据库索引与迁移规范**：`file_name` / `folder_path` 等加索引；把启动时 `ALTER` 迁移改为版本化迁移流程；
4. **MinIO 接入**（满足触发条件后实施）：`STORAGE_BACKEND=local|minio` 开关（默认 local、不可用时降级）；bucket 初始化（`bucket_exists` + `make_bucket`）；解析临时目录方案；`minio_path` 语义改为对象 key；密钥只走 `.env` / compose；
5. **评分策略落地**：短答案规范化精确匹配、长答案语义评分 + 固定校准集验证阈值；LLM 裁判防位置 / 长度偏差并保留人工抽查（BRD §8.22 FR-DS-SRC-003）；
6. **日志 / 监控 / 审计**：job 卡死检测（超时置 failed）、token 计数与告警、审计日志查询视图；
7. **依赖安全**：锁版本并做漏洞扫描（PyMuPDF / openpyxl / python-docx / minio 等）；Docker 镜像最小化与安全基线；
8. **多实例化准备**：`confirm_token` 内存态改 Redis；EIU FAISS 索引多实例共享 / 重建策略；后台线程任务改分布式任务队列。

### P2（业务口径确认，对应 BRD §18）

9. 上传评测集实际格式与字段校验、多轮场景是否纳入 MVP；
10. 公共评测集库首批 QA 数据集与评测维度体系（维度暂不固定）；
11. 语义评分阈值与固定校准集构建方案；
12. 三套量化质量评估（EIU / QA / 上传评测集）提示性门禁阈值与界面展示范围；
13. 多轮 `memory` / `coherence` 评分规则与人工抽查比例；
14. 其余 BRD §18 确认项（数据规模、扫描件比例、外部模型允许、部署形态等）。

---

## C. 归档说明（已删除的讨论文档）

以下讨论产物价值已并入对应文档后删除（git 历史可追溯）：

| 已删除文件 | 价值去向 |
|---|---|
| `evaluation_dataset_brd_additions.md` | 已并入 BRD V1.3（§8.22 / §8.23 及各功能小节） |
| `evaluation_dataset_discussion_summary.md` | 四项决策已并入 BRD V1.3 + 本文档 |
| `evaluation_scoring_strategy.md` | 评分口径已并入 BRD §8.22 FR-DS-SRC-003；研究依据见 BRD §19 |
| `docs/upload-reupload-plan.md` | 设计要点已并入本文档 A 节 + m01 README §2.8 |
| `docs/demo-guide.md` | 占位文件，启动 / 部署说明以根 README 为准 |

---

## D. 保留文档索引

| 文档 | 用途 |
|---|---|
| `evaluation_dataset_platform_brd.md`（仓库根） | 业务需求书 V1.3 |
| `README.md`（仓库根） | 启动 / 部署 / 端口约定 |
| `docs/production-readiness-todo.md` | 本文档：生产化前代办 |
| `docs/architecture.md` / `docs/api.md` / `docs/data-model.md` | 架构 / 接口 / 数据模型 |
| `modules/*/README.md` | 各模块技术文档（以代码为准） |
