import os
from pathlib import Path

from pydantic import BaseModel

# 加载项目根 .env（gitignore 已忽略，存放本机密钥），不覆盖已有环境变量。
# 容器内直接由 compose/环境变量注入，不强制依赖 python-dotenv。
try:  # pragma: no cover - 可选依赖
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


class Settings(BaseModel):
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "evalforge")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "evalforge")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "evalforge")
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "minio")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "minio12345")
    faiss_index_path: str = os.getenv("FAISS_INDEX_PATH", "storage/faiss.index")
    embedding_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh-v1.5")
    # 文档接入限制（README FR-DOC-005 / §2.6）
    max_file_size: int = int(os.getenv("MAX_FILE_SIZE", str(50 * 1024 * 1024)))  # 50MB
    allowed_extensions: list[str] = [
        ext.strip().lower()
        for ext in os.getenv("ALLOWED_EXTENSIONS", ".txt,.md,.pdf,.docx").split(",")
        if ext.strip()
    ]
    # 默认按 MYSQL_* 拼出连接串；若显式设置 DATABASE_URL 则优先
    database_url: str = os.getenv("DATABASE_URL") or (
        f"mysql+pymysql://{mysql_user}:{mysql_password}@"
        f"{mysql_host}:{mysql_port}/{mysql_database}"
    )
    # LLM（OpenAI 兼容 API，用于 M02 EIU 抽取 / 后续题目生成）
    # LLM_API_KEY 为占位符 "sk-xxx" 或缺少 openai 库时，M02 自动切换为离线确定性抽取
    llm_api_base: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "sk-xxx")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))  # 抽取任务需低温
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    minio_bucket: str = os.getenv("MINIO_BUCKET", "evalforge")
    storage_root: Path = Path(os.getenv("STORAGE_ROOT", "storage"))
    state_file: Path = Path(os.getenv("STATE_FILE", "storage/demo_state.json"))
    raw_dir: Path = Path(os.getenv("RAW_DIR", "storage/raw"))
    parsed_dir: Path = Path(os.getenv("PARSED_DIR", "storage/parsed"))
    index_dir: Path = Path(os.getenv("INDEX_DIR", "storage/index"))


settings = Settings()
