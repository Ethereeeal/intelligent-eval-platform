"""m03 评测集生成：FastAPI 路由层（README §6 API 接口）。

路由为薄壳：解析请求体 → 调 PipelineService → 转响应模型。
业务逻辑全部在 services/pipeline.py。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from modules.m03_generation.schemas import (
    CaseDetailOut,
    CaseOut,
    CaseUpdateRequest,
    GenerateCasesRequest,
    GenerateCasesResponse,
    GenerateSingleCaseRequest,
    UploadQAPairRequest,
    VariationRequest,
)
from modules.m03_generation.services.pipeline import PipelineService

pipeline_service = PipelineService()

# 路由规划（避免与 m01 的 /api/corpus 基础 CRUD 冲突，均挂在更深路径）
generation_router = APIRouter(prefix="/api/corpus", tags=["generation"])
eiu_router = APIRouter(prefix="/api/eiu", tags=["generation"])
cases_router = APIRouter(prefix="/api/cases", tags=["cases"])


# ----------------------------------------------------------------------
# 批量生成：POST /api/corpus/{corpus_id}/cases/generate
# ----------------------------------------------------------------------
@generation_router.post("/{corpus_id}/cases/generate", response_model=GenerateCasesResponse)
def generate_cases(
    corpus_id: int,
    payload: GenerateCasesRequest,
    document_id: int | None = Query(default=None, description="指定文档时仅生成该文档的问答对（单文档隔离）。"),
):
    if pipeline_service.database.get_corpus(corpus_id) is None:
        raise HTTPException(status_code=404, detail="corpus not found")
    try:
        if document_id is not None:
            # 单文档隔离：仅抽取当前文档 EIU、不重抽其他文档、不重复生成
            return pipeline_service.generate_cases_for_document(
                corpus_id=corpus_id,
                document_id=document_id,
                angles=payload.angles,
                include_variations=payload.include_variations,
                variation_count=payload.variation_count,
                dry_run=payload.dry_run,
            )
        return pipeline_service.generate_cases_for_corpus(
            corpus_id,
            angles=payload.angles,
            include_variations=payload.include_variations,
            variation_count=payload.variation_count,
            dry_run=payload.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ----------------------------------------------------------------------
# 评测样本列表：GET /api/corpus/{corpus_id}/cases
# ----------------------------------------------------------------------
@generation_router.get("/{corpus_id}/cases", response_model=list[CaseOut])
def list_cases(
    corpus_id: int,
    priority: str | None = Query(None),
    type: str | None = Query(None, alias="question_type"),
    difficulty: str | None = Query(None),
    status: str | None = Query(None),
):
    if pipeline_service.database.get_corpus(corpus_id) is None:
        raise HTTPException(status_code=404, detail="corpus not found")
    return pipeline_service.list_cases(
        corpus_id,
        priority=priority,
        question_type=type,
        difficulty=difficulty,
        status=status,
    )


# ----------------------------------------------------------------------
# 单 EIU 生成：POST /api/eiu/{eiu_id}/generate-case
# ----------------------------------------------------------------------
@eiu_router.post("/{eiu_id}/generate-case")
def generate_case_for_eiu(eiu_id: int, payload: GenerateSingleCaseRequest):
    try:
        return pipeline_service.generate_case_for_eiu(
            eiu_id,
            angle=payload.angle,
            include_variations=payload.include_variations,
            variation_count=payload.variation_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ----------------------------------------------------------------------
# 路径 2：用户上传问答对
# POST /api/cases/generate-from-upload（需定义在 /{case_id} 之前）
# ----------------------------------------------------------------------
@cases_router.post("/generate-from-upload")
def generate_from_upload(payload: UploadQAPairRequest):
    try:
        return pipeline_service.generate_from_upload(
            corpus_id=payload.corpus_id,
            document_id=payload.document_id,
            question=payload.question,
            answer=payload.answer,
            question_type=payload.question_type,
            difficulty=payload.difficulty,
            content_priority=payload.content_priority,
            evidence=[e.model_dump() for e in payload.evidence] if payload.evidence else None,
            generate_variations=payload.generate_variations,
            variation_count=payload.variation_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ----------------------------------------------------------------------
# 样本详情 / 编辑 / 删除
# ----------------------------------------------------------------------
@cases_router.get("/{case_id}", response_model=CaseDetailOut)
def get_case(case_id: int):
    case = pipeline_service.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case


@cases_router.put("/{case_id}", response_model=CaseDetailOut)
def update_case(case_id: int, payload: CaseUpdateRequest):
    fields = payload.model_dump(exclude_unset=True)
    if "evidence" in fields and fields["evidence"] is not None:
        fields["evidence"] = [e.model_dump() for e in fields["evidence"]]
    updated = pipeline_service.update_case(case_id, **fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="case not found")
    return updated


@cases_router.delete("/{case_id}")
def delete_case(case_id: int):
    deleted = pipeline_service.delete_case(case_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="case not found")
    return {"case_id": case_id, "status": "retired"}


# ----------------------------------------------------------------------
# 泛化/改写：POST /api/cases/{case_id}/variations
# ----------------------------------------------------------------------
@cases_router.post("/{case_id}/variations")
def generate_variations(case_id: int, payload: VariationRequest):
    try:
        return pipeline_service.generate_variations_for_case(
            case_id, count=payload.count, styles=payload.styles
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
