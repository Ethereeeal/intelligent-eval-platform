# 前后端完整联调

## 联调边界

联调环境使用独立的 Compose 项目、端口和数据卷，不读取当前 Demo 的 MySQL/MinIO 数据。完整链路覆盖：

`文档上传 → EIU 抽取 → 问答生成 → 质量门禁 → 冻结版本 → 三来源组合 → 批量评测 → 结果与 Excel 导出`

测试数据直接复用 `data/template`：上传其中体积最小的 DOCX，并从 `qa_pairs.json` 读取少量真实字段样例建立上传库和公共库。

## 启动与执行

```powershell
docker compose -f deploy/docker-compose.integration.yml up -d --build
python tests/integration/full_chain.py
```

默认评测适配器是 `deepseek`。脚本从不会提交到 Git 的 `.env` 读取：

- `LLM_API_BASE`：DeepSeek 的 OpenAI 兼容 API Base；
- `LLM_API_KEY`：有效密钥，不能是 `sk-xxx` 等占位值；
- `LLM_MODEL`：实际可调用的模型名。

M02-M04 的生成与质检固定走联调桩，以保证回归稳定；M08 评测运行会把上述配置仅随本地请求传给后端，后端持久化前会剔除 API Key。日志、报告和仓库文件均不得记录密钥。

如果只诊断平台编排、不调用 DeepSeek，可显式使用：

```powershell
python tests/integration/full_chain.py --evaluation-adapter stub
```

联调入口为 `http://localhost:18080`，后端直连入口为 `http://localhost:18000`，外部服务桩为 `http://localhost:18090`。当前 Demo 的 `8080/8000` 不受影响。

## 验收标准

- 异步 job 和评测 run 的进度只能前进，最终为 100%；
- 生成库、上传库、公共库三种来源均能解析到可执行评测集；
- 结果数与运行样本数一致，刷新后仍可查询；
- 完整 Excel 行数与结果一致，筛选导出只包含指定行；
- 中文文档名、运行名和报告文件名不乱码；
- 目标智能体返回错误 JSON 时，本轮仍能收敛到完成状态并记录错误。

需要销毁联调数据时，先确认目标文件确为 `deploy/docker-compose.integration.yml`，再执行：

```powershell
docker compose -f deploy/docker-compose.integration.yml down -v
```
