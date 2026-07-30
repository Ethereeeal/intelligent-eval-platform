# 本地 BGE 模型目录

本目录用于放置**手动下载**的 BGE 模型。运行时会由容器挂载到 `/app/models` 并直接加载，
**不依赖构建期或运行期的 HuggingFace / hf-mirror 联网**（见 `deploy/docker-compose.yml` 的
`../models:/app/models` 挂载与 `LOCAL_MODELS_DIR` 环境变量）。

> 不要把模型权重提交进 Git：它们体积大且不参与镜像构建（已通过项目根 `.dockerignore` 排除）。

## 需要下载的模型

| 模型 | 用途 | 下载源（ModelScope，国内直连推荐） | 下载源（hf-mirror） |
|---|---|---|---|
| `bge-small-zh-v1.5` | 向量化嵌入（语义分段 / FAISS 索引） | https://modelscope.cn/models/BAAI/bge-small-zh-v1.5 | https://hf-mirror.com/BAAI/bge-small-zh-v1.5/tree/main |
| `bge-reranker-v2-m3` | 重排（CrossEncoder） | https://modelscope.cn/models/BAAI/bge-reranker-v2-m3 | https://hf-mirror.com/BAAI/bge-reranker-v2-m3/tree/main |

> **下载方式（推荐 ModelScope，国内无需折腾镜像变量）**：
> ```bash
> # 用装了 modelscope 的那个 python（可能与系统 python3 不同，注意环境一致性）
> python3 -c "
> from modelscope import snapshot_download
> snapshot_download('BAAI/bge-small-zh-v1.5', local_dir='models/bge-small-zh-v1.5')
> snapshot_download('BAAI/bge-reranker-v2-m3', local_dir='models/bge-reranker-v2-m3')
> "
> ```
> 注意：`huggingface-cli` 已废弃，新版 `hf` CLI（Rust 版）**不读取 `HF_ENDPOINT`**，
> 会直连被墙的 huggingface.co 而失败；如需走 HuggingFace 源，请用 `huggingface_hub` 库的
> Python API（`snapshot_download` + `export HF_ENDPOINT=https://hf-mirror.com`），它一定认该变量。

## 放置方式

将每个模型的所有文件（`config.json`、`model.safetensors` 或 `pytorch_model.bin`、
`tokenizer*.json`、`sentencepiece.bpe.model` 等）放在对应的子目录下。

> 注意：嵌入模型 `bge-small-zh-v1.5` 需要 sentence-transformers 专属结构文件
> `modules.json` 与 `1_Pooling/config.json`（`SentenceTransformer` 靠它们组装 pooling 层）。
> 从 ModelScope 下载的 `bge-small-zh-v1.5` 通常已包含这两个文件；重排模型 `bge-reranker-v2-m3`
> **不需要**这两个文件（`CrossEncoder` 直接按 transformers 模型加载），缺失属正常。

```
models/
├── bge-small-zh-v1.5/        # 需含 modules.json 与 1_Pooling/config.json
│   ├── config.json
│   ├── model.safetensors
│   ├── tokenizer.json
│   ├── tokenizer_config.json
│   ├── sentencepiece.bpe.model
│   ├── 1_Pooling/
│   │   └── config.json
│   └── modules.json
└── bge-reranker-v2-m3/      # CrossEncoder 加载，无需 modules.json / 1_Pooling
    ├── config.json
    ├── model.safetensors
    ├── tokenizer.json
    ├── tokenizer_config.json
    └── sentencepiece.bpe.model
```

## 加载逻辑

- `modules/m01_data_foundation/services/embedding.py` 优先从
  `$LOCAL_MODELS_DIR/bge-small-zh-v1.5`（默认 `/app/models/bge-small-zh-v1.5`）加载，
  目录不存在时才回退到 HuggingFace Hub 在线下载。
- `modules/shared/services/rerank.py` 同理加载 `bge-reranker-v2-m3`。

## 生效方式

模型文件放好后，重启 backend 容器即可：

```bash
docker compose -f deploy/docker-compose.yml restart backend
```
