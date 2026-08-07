import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from modules.m01_data_foundation.api import (
    corpus_router,
    documents_router,
    jobs_router,
)
from modules.m02_eiu_coverage.api import corpus_eiu_router, eiu_router
from modules.m03_generation.api import (
    cases_router,
    generation_router,
)
from modules.m03_generation.api import (
    eiu_router as generation_eiu_router,
)
from modules.m04_quality_governance.api import quality_router
from modules.m05_dataset_lifecycle.api import router as dataset_lifecycle_router
from modules.m07_smart_qa.api import router as chat_router
from modules.shared.core.logging_config import configure_logging
from modules.shared.services.database import DatabaseService


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化日志（参考日志规约：统一日志入口，禁止散落的 print）
    configure_logging()
    logging.getLogger("uvicorn.error").info("EvalForge backend starting")
    # 启动时按 ORM 定义建表（MySQL / SQLite 通用）
    DatabaseService().create_all()
    yield


app = FastAPI(title="EvalForge Backend", version="0.2.0", lifespan=lifespan)

# CORS — allow local dev frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router)
app.include_router(corpus_router)
app.include_router(jobs_router)
app.include_router(corpus_eiu_router)
app.include_router(eiu_router)
app.include_router(generation_router)
app.include_router(generation_eiu_router)
app.include_router(cases_router)
app.include_router(quality_router)
app.include_router(dataset_lifecycle_router)
app.include_router(chat_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "version": "0.2.0"}
