from fastapi import APIRouter

from app.api.document import router as document_router

router = APIRouter()
router.include_router(document_router)
