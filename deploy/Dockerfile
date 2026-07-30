FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/root/.cache/huggingface \
    HF_HUB_OFFLINE=1

WORKDIR /app

# 构建上下文为项目根，复制全部源码（含 modules/）
COPY . .

# 先写入全局 pip 配置（超时 600s / 重试 10 / 国内镜像），对所有后续 pip 安装生效，
# 以对抗容器内访问 pypi.org / download.pytorch.org / files.pythonhosted.org 的网络抖动
# （之前 torch 步骤因默认超短超时导致 155MB 大轮子 ReadTimeout）。
RUN pip config set global.timeout 600 \
 && pip config set global.retries 10 \
 && pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \
 && pip config set global.extra-index-url "https://mirrors.cloud.tencent.com/pypi/simple/ https://mirrors.tuna.tsinghua.edu.cn/pypi/simple/"
# torch 走 CPU 专用源：当前运行环境无 GPU（无 CUDA），用 +cpu 轮子避免
# 拉取 nvidia-cudnn / cuda-toolkit 等多余 CUDA 依赖。后续若有 GPU 环境，
# 再改回默认源或指定对应 CUDA 版本的 torch。全局超时/重试已在上一步配置，
# 再套一层整条命令重试循环以对抗 torch 大轮子的瞬时 ReadTimeout。
RUN for i in 1 2 3 4 5; do \
      pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch && break \
      || echo "torch install attempt $i failed, retrying in 15s..." && sleep 15; \
    done
# 其余依赖走国内镜像源（已在全局配置中设置 aliyun + 腾讯云 + 清华），
# 并套一层整条命令重试循环以对抗瞬时网络抖动。torch 已装好，不会重复拉 CUDA 版。
RUN for i in 1 2 3 4 5; do \
      pip install --no-cache-dir -r deploy/requirements.txt && break \
      || echo "pip install attempt $i failed, retrying in 15s..." && sleep 15; \
    done

# BGE 模型（bge-small-zh-v1.5 与 bge-reranker-v2-m3）不在构建期下载烘焙，
# 改由宿主机 ./models 目录挂载进容器（见 docker-compose.yml 的 ../models:/app/models），
# 运行时由 embedding.py / rerank.py 直接从 /app/models/<模型名> 本地目录加载，
# 完全不依赖构建期或运行期的 HuggingFace / hf-mirror 联网。模型文件由使用者手动下载
# （下载方式与目录结构见 models/README.md）。
# 注意：HF_HUB_OFFLINE=1 仍开启，确保本地目录缺失时也不会意外发起网络请求。

EXPOSE 8000
CMD ["uvicorn", "modules.shared.main:app", "--host", "0.0.0.0", "--port", "8000"]
