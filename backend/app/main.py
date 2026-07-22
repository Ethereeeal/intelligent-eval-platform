from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="EvalForge Backend", version="0.1.0")
app.include_router(router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
