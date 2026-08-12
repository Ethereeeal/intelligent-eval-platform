"""m03 评测集生成：FastAPI 路由层（按文件维度，无 corpus）。

路由为薄壳：解析请求体 → 调 PipelineService → 转响应模型。
业务逻辑全部在 services/pipeline.py。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Response

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

generation_router = APIRouter(prefix="/api/cases", tags=["generation"])
eiu_router = APIRouter(prefix="/api/eiu", tags=["generation"])
cases_router = APIRouter(prefix="/api/cases", tags=["cases"])


# ----------------------------------------------------------------------
# 批量生成：POST /api/cases/generate（按 document_id 或全量）
# ----------------------------------------------------------------------
@generation_router.post("/generate", response_model=GenerateCasesResponse)
def generate_cases(
    payload: GenerateCasesRequest,
    document_id: int | None = Query(default=None, description="指定文档时仅生成该文档的问答对（单文档隔离）。"),
):
    try:
        if document_id is not None:
            # 单文档隔离：仅抽取当前文档 EIU、不重抽其他文档、不重复生成
            return pipeline_service.generate_cases_for_document(
                document_id=document_id,
                angles=payload.angles,
                include_variations=payload.include_variations,
                variation_count=payload.variation_count,
                dry_run=payload.dry_run,
            )
        return pipeline_service.generate_cases_for_corpus(
            angles=payload.angles,
            include_variations=payload.include_variations,
            variation_count=payload.variation_count,
            dry_run=payload.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ----------------------------------------------------------------------
# 生成进度：GET /api/cases/generate-progress（前端「运行监测」轮询百分比）
# ----------------------------------------------------------------------
@generation_router.get("/generate-progress")
def generate_progress(
    document_id: int | None = Query(default=None, description="指定文档时返回该文档生成进度，缺省返回全量任务进度。"),
):
    return pipeline_service.get_generate_progress(document_id=document_id)


# ----------------------------------------------------------------------
# 评测样本列表：GET /api/cases（全量）
# ----------------------------------------------------------------------
@cases_router.get("", response_model=list[CaseOut])
def list_cases_all(
    priority: str | None = Query(None),
    type: str | None = Query(None, alias="question_type"),
    difficulty: str | None = Query(None),
    status: str | None = Query(None),
    folder_path: str | None = Query(None, description="按问答对库目录过滤（与输入文档库同构）。"),
    purpose: str | None = Query(None, description="basic=基础问题，gen=泛化问题。"),
):
    """返回全部问答对，前端按 document_id / folder_path 聚合到目录树。"""
    return pipeline_service.list_cases(
        priority=priority,
        question_type=type,
        difficulty=difficulty,
        status=status,
        folder_path=folder_path,
        purpose=purpose,
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
# POST /api/cases/generate-from-upload
# ----------------------------------------------------------------------
@cases_router.post("/generate-from-upload")
def generate_from_upload(payload: UploadQAPairRequest):
    try:
        return pipeline_service.generate_from_upload(
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
@cases_router.delete("/document/{document_id}")
def delete_cases_by_document(document_id: int):
    """清空指定文档下的全部问答对（保留文档与 EIU，可重新生成）。"""
    deleted = pipeline_service.database.delete_generated_cases_by_document(
        document_id=document_id
    )
    return {"document_id": document_id, "deleted": deleted}


@cases_router.get("/export-folder")
def export_folder(
    folder_path: str | None = Query(None, description="目录相对「问答对库」根路径；缺省导出整个问答对库。"),
    recursive: bool = Query(True, description="是否递归导出子目录。"),
    purpose: str | None = Query(None, description="basic/gen 仅导出某类；缺省全部。"),
):
    """导出文件夹（带目录结构）。返回 JSON，内含按目录层级组织的问答对。

    注意：本路由必须声明在 GET /{case_id} 之前，否则 FastAPI 会把
    「export-folder」当作 case_id 去匹配 /{case_id}，导致 422。
    """
    payload = pipeline_service.export_cases_folder(
        folder_path=folder_path, recursive=recursive, purpose=purpose
    )
    # 文件名用 folder_path 推导，但可能含中文 → 用 RFC 5987 的 filename* 编码，
    # 避免 Response 按 latin-1 编码中文时报 UnicodeEncodeError。
    raw_name = "qa_export.json" if not folder_path else f"qa_{folder_path.replace('/', '_')}.json"
    ascii_name = raw_name.encode("ascii", "ignore").decode() or "qa_export.json"
    from urllib.parse import quote
    encoded = quote(raw_name, safe="")
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"
        },
    )


# ----------------------------------------------------------------------
# 按文档（文件目录维度）列出问答对 —— 不依赖 corpus
# 注意：静态段路由（/document/...）必须声明在 /{case_id} 之前，避免被抢占。
# ----------------------------------------------------------------------
@cases_router.get("/document/{document_id}", response_model=list[CaseOut])
def list_cases_by_document(
    document_id: int,
    priority: str | None = Query(None),
    type: str | None = Query(None, alias="question_type"),
    difficulty: str | None = Query(None),
    status: str | None = Query(None),
):
    """按文件（document_id）列出其问答对，用于「我的文件库」目录树组织，无需 corpus。"""
    if pipeline_service.database.find_document_by_id(document_id) is None:
        raise HTTPException(status_code=404, detail="document not found")
    return pipeline_service.list_cases(
        document_id=document_id,
        priority=priority,
        question_type=type,
        difficulty=difficulty,
        status=status,
    )


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


# ----------------------------------------------------------------------
# 问答对库目录操作：移动到文件夹 / 重命名 / 导出文件夹（与输入文档库同构）
# ----------------------------------------------------------------------
@cases_router.post("/{case_id}/move")
def move_case(case_id: int, folder_path: str | None = Query(None, description="目标目录相对「问答对库」根路径，空串=根目录。")):
    """把问答对集移动到指定目录（按 folder_path 组织，与文档同构）。"""
    updated = pipeline_service.update_case(case_id, folder_path=folder_path or "")
    if updated is None:
        raise HTTPException(status_code=404, detail="case not found")
    return {"case_id": case_id, "folder_path": folder_path or "", "status": "moved"}


@cases_router.post("/{case_id}/rename")
def rename_case(case_id: int, new_name: str = Query(..., description="新的问题文本（重命名=改问题/种子题干）。")):
    """重命名问答对集（改写 question 字段，与输入库 rename 改 file_name 同构）。"""
    updated = pipeline_service.update_case(case_id, question=new_name)
    if updated is None:
        raise HTTPException(status_code=404, detail="case not found")
    return {"case_id": case_id, "question": new_name, "status": "renamed"}
