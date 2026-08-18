import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from modules.m01_data_foundation.api import (
    documents_router,
    folders_router,
    jobs_router,
)
from modules.m02_eiu_coverage.api import eiu_router
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
from modules.shared.core.config import settings
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

# CORS — 前端经 nginx 同源代理（8080）访问时无需跨域；直连后端按白名单放行
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_token_auth(request: Request, call_next):
    """P0 访问控制：设置 API_TOKEN 后启用，未带有效令牌的 /api/* 请求返回 401。

    Demo 默认 API_TOKEN 为空（鉴权关闭，保持本地联调不变）；生产环境必须设置
    API_TOKEN，前端经 nginx 注入请求头或直接带 Bearer Token 访问。
    """
    if not settings.api_token:
        return await call_next(request)
    path = request.url.path
    if request.method == "OPTIONS" or path in ("/health", "/docs", "/openapi.json", "/redoc"):
        return await call_next(request)
    if not path.startswith("/api/"):
        return await call_next(request)
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        supplied = auth_header[len("Bearer "):].strip()
        if secrets.compare_digest(supplied, settings.api_token):
            return await call_next(request)
    x_token = request.headers.get("x-api-token", "")
    if x_token and secrets.compare_digest(x_token.strip(), settings.api_token):
        return await call_next(request)
    return JSONResponse(status_code=401, content={"detail": "未授权访问，请提供有效的 API Token"})


app.include_router(documents_router)
app.include_router(folders_router)
app.include_router(jobs_router)
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
