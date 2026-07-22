from pydantic import BaseModel
from pathlib import Path


class Settings(BaseModel):
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "evalforge"
    mysql_password: str = "evalforge"
    mysql_database: str = "evalforge"
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minio"
    minio_secret_key: str = "minio12345"
    faiss_index_path: str = "storage/faiss.index"
    embedding_model_name: str = "BAAI/bge-small-zh-v1.5"
    database_url: str = "sqlite:///storage/evalforge.db"
    minio_bucket: str = "evalforge"
    storage_root: Path = Path("storage")
    state_file: Path = Path("storage/demo_state.json")
    raw_dir: Path = Path("storage/raw")
    parsed_dir: Path = Path("storage/parsed")
    index_dir: Path = Path("storage/index")


settings = Settings()
