import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_ROOT = BASE_DIR.parent / "storage"
RAW_DIR = STORAGE_ROOT / "raw"
PARSED_DIR = STORAGE_ROOT / "parsed"
INDEX_DIR = STORAGE_ROOT / "index"
STATE_FILE = STORAGE_ROOT / "state.json"
DATABASE_URL = f"sqlite:///{STORAGE_ROOT / 'db.sqlite'}"

# LLM 配置请通过环境变量设置，不要直接写入代码。
LLM_API_URL = os.getenv("LLM_API_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

class Settings:
    storage_root: Path = STORAGE_ROOT
    raw_dir: Path = RAW_DIR
    parsed_dir: Path = PARSED_DIR
    index_dir: Path = INDEX_DIR
    state_file: Path = STATE_FILE
    database_url: str = DATABASE_URL
    llm_api_url: str = LLM_API_URL
    llm_api_key: str = LLM_API_KEY
    llm_model: str = LLM_MODEL


settings = Settings()
