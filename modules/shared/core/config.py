import os

from pydantic import BaseModel
from pathlib import Path


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
    # 默认按 MYSQL_* 拼出连接串；若显式设置 DATABASE_URL 则优先
    database_url: str = os.getenv("DATABASE_URL") or (
        f"mysql+pymysql://{mysql_user}:{mysql_password}@"
        f"{mysql_host}:{mysql_port}/{mysql_database}"
    )
    minio_bucket: str = os.getenv("MINIO_BUCKET", "evalforge")
    storage_root: Path = Path(os.getenv("STORAGE_ROOT", "storage"))
    state_file: Path = Path(os.getenv("STATE_FILE", "storage/demo_state.json"))
    raw_dir: Path = Path(os.getenv("RAW_DIR", "storage/raw"))
    parsed_dir: Path = Path(os.getenv("PARSED_DIR", "storage/parsed"))
    index_dir: Path = Path(os.getenv("INDEX_DIR", "storage/index"))


settings = Settings()
