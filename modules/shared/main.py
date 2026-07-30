from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from modules.m01_data_foundation.api import (
    corpus_router,
    documents_router,
    jobs_router,
)
from modules.m07_smart_qa.api import router as chat_router
from modules.shared.services.database import DatabaseService


@asynccontextmanager
async def lifespan(app: FastAPI):
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
app.include_router(chat_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "version": "0.2.0"}
