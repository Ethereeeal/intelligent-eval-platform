FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 构建上下文为项目根，复制全部源码（含 modules/）
COPY . .

# 安装依赖（完整清单见 deploy/requirements.txt）
RUN pip install --no-cache-dir -r deploy/requirements.txt

EXPOSE 8000
CMD ["uvicorn", "modules.shared.main:app", "--host", "0.0.0.0", "--port", "8000"]
