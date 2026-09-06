"""M02 — EIU 抽取与覆盖规划 API（SPEC §7，按文件维度，无 corpus）。

路由：
  POST   /api/eiu/extract              异步触发 EIU 抽取（按 document_id 或全量，返回 job_id）
  GET    /api/eiu                       全量 EIU 清单（支持过滤）
  GET    /api/eiu/document/{id}         按文件列出 EIU
  GET    /api/eiu/coverage              覆盖率报告（全量）
  GET    /api/eiu/gaps                  未覆盖 EIU 清单（全量）
  POST   /api/eiu/coverage              计算覆盖率并落库，返回带 report_id 的报告
  GET    /api/eiu/{eiu_id}              EIU 详情（含原文上下文）
  PUT    /api/eiu/{eiu_id}              手动编辑 EIU
  DELETE /api/eiu/{eiu_id}              归档至已排除（保留证据，只读）
"""
from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException, Query

from modules.m02_eiu_coverage.schemas import (
    CoverageReport,
    CoverageReportOut,
    DeleteResponse,
    EiuDetail,
    EiuExtractResponse,
    EiuListResponse,
    EiuManualIncludeRequest,
    EiuMergeRequest,
    EiuOut,
    EiuSplitRequest,
    EiuUpdate,
    GapListResponse,
)
from modules.m02_eiu_coverage.services.coverage import (
    compute_coverage,
    compute_gaps,
    save_coverage_report,
)
from modules.m02_eiu_coverage.services.claim_audit import analyse_claim_relationships
from modules.m02_eiu_coverage.services.eiu_extractor import EiuExtractorService
from modules.m02_eiu_coverage.services.eiu_gate_policy import QUALITY_POLICY_VERSION, EiuGatePolicy
from modules.m02_eiu_coverage.services.eiu_quality import EiuQualityEvaluator
from modules.shared.services.database import EIU_TYPES, DatabaseService

# 全局（按文件维度）：/api/eiu/...
eiu_router = APIRouter(prefix="/api/eiu", tags=["eiu"])

database = DatabaseService()
extractor_service = EiuExtractorService()

_GATE_FIELDS = {
    "content_priority", "is_questionable", "exclusion_reason", "quality_status",
    "route_color", "route_reasons", "review_action", "importance_signals",
    "importance_reason", "canonical_intent_key", "auto_disposition",
    "quality_policy_version", "evaluation_profiles",
}


def _recheck_document_gate(*, document_id: int, edited_eiu_id: int) -> dict:
    """人工编辑后重跑三项 EIU 门禁与全文相对重要性，绝不直接转绿。"""
    document = database.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    blocks = database.get_document_blocks(document_id)
    by_block_id = {int(block["block_id"]): block for block in blocks}
    items = database.list_eius(document_id=document_id)
    evaluator = EiuQualityEvaluator(blocks)
    rechecked: list[dict] = []
    for item in items:
        if int(item["eiu_id"]) == edited_eiu_id:
            source = by_block_id.get(int(item["block_id"]))
            if source is None:
                raise HTTPException(status_code=422, detail="EIU 对应原文 Block 不存在，无法重新核验")
            item = evaluator.annotate(item, source)
        rechecked.append(item)
    gated, findings = EiuGatePolicy(extractor_service.llm).apply_document(
        document=document,
        items=rechecked,
        blocks=blocks,
    )
    for item in gated:
        database.update_eiu(
            int(item["eiu_id"]),
            **{field: item[field] for field in _GATE_FIELDS if field in item},
        )
    database.replace_document_quality_findings(
        document_id=document_id,
        findings=findings,
        policy_version=QUALITY_POLICY_VERSION,
    )
    result = database.get_eiu(edited_eiu_id)
    if result is None:
        raise HTTPException(status_code=404, detail="eiu not found")
    return result


def _documents_scope(document_id: int | None) -> list[dict]:
    documents = database.list_documents()
    if document_id is not None:
        documents = [d for d in documents if d["document_id"] == document_id]
    return documents


def _count_paragraph_blocks(document_id: int | None = None) -> int:
    total = 0
    for document in _documents_scope(document_id):
        total += sum(
            1
            for block in database.get_document_blocks(document["document_id"])
            if block["block_type"] != "title"
        )
    return total


# ----------------------------------------------------------------------
# 异步抽取（按文件维度）
# ----------------------------------------------------------------------
@eiu_router.post("/extract", response_model=EiuExtractResponse, status_code=202)
def trigger_eiu_extract(
    document_id: int | None = Query(default=None, description="指定文档时仅抽取该文档（单文档隔离），否则全量抽取"),
) -> EiuExtractResponse:
    if document_id is not None and database.find_document_by_id(document_id) is None:
        raise HTTPException(status_code=404, detail="document not found")
    job_id = database.save_job(document_id=document_id or 0, job_type="eiu_extract")
    database.update_job(
        job_id, status="running", phase="queued", progress=0, message="任务已创建，准备抽取"
    )

    total = _count_paragraph_blocks(document_id=document_id)
    if total == 0:
        database.update_job(
            job_id, status="completed", phase="done", progress=100,
            message="无可处理的段落", finished=True,
        )
        return EiuExtractResponse(
            job_id=job_id, status="completed", message="无可处理的段落"
        )

    database.update_job(job_id, progress=0, message=f"开始 EIU 抽取，共 {total} 个段落 Block")
    target = extractor_service.extract_document if document_id is not None else extractor_service.extract_corpus
    thread_kwargs = (
        {"document_id": document_id, "job_id": job_id}
        if document_id is not None
        else {"job_id": job_id}
    )
    thread = threading.Thread(target=target, kwargs=thread_kwargs, daemon=True)
    thread.start()
    return EiuExtractResponse(
        job_id=job_id,
        status="running",
        message=f"开始 EIU 抽取，共 {total} 个段落 Block",
    )


# ----------------------------------------------------------------------
# EIU 清单 / 覆盖率 / 未覆盖清单
# ----------------------------------------------------------------------
@eiu_router.get("", response_model=EiuListResponse)
def list_eius_all(
    type: list[str] | None = Query(None, description="EIU 类型，可重复"),
    priority: list[str] | None = Query(None, description="优先级 P0/P1/P2，可重复"),
    questionable: bool | None = Query(None, description="是否可出题"),
    section: str | None = Query(None, description="按章节路径模糊过滤"),
    document_id: int | None = Query(None, description="按文档过滤"),
    disposition: list[str] | None = Query(None, description="自动处置状态 green/yellow/red，可重复"),
) -> EiuListResponse:
    items = database.list_eius(
        eiu_type=type,
        priority=priority,
        questionable=questionable,
        section=section,
        document_id=document_id,
        disposition=disposition,
    )
    return EiuListResponse(total=len(items), items=items)


@eiu_router.get("/document/{document_id}", response_model=EiuListResponse)
def list_eius_by_document(
    document_id: int,
    type: list[str] | None = Query(None, description="EIU 类型，可重复"),
    priority: list[str] | None = Query(None, description="优先级 P0/P1/P2，可重复"),
    questionable: bool | None = Query(None, description="是否可出题"),
    disposition: list[str] | None = Query(None, description="自动处置状态 green/yellow/red，可重复"),
) -> EiuListResponse:
    """按文件（document_id）列出其 EIU，用于「我的文件库」目录树组织，无需 corpus。"""
    if database.find_document_by_id(document_id) is None:
        raise HTTPException(status_code=404, detail="document not found")
    items = database.list_eius(
        eiu_type=type,
        priority=priority,
        questionable=questionable,
        document_id=document_id,
        disposition=disposition,
    )
    return EiuListResponse(total=len(items), items=items)


@eiu_router.get("/coverage", response_model=CoverageReport)
def get_coverage() -> CoverageReport:
    return CoverageReport(**compute_coverage())


@eiu_router.post("/coverage", response_model=CoverageReportOut, status_code=201)
def persist_coverage() -> CoverageReportOut:
    """计算覆盖率并落库为 coverage_report，返回带 report_id 的报告（供 m05 冻结外键引用）。"""
    save_coverage_report()
    row = database.get_latest_coverage_report()
    # 历史 coverage_report 表尚未持久化候选质量分层字段；响应中补入当前确定性计数，
    # 避免 POST 与 GET /coverage 对同一时点返回不同口径。
    current = compute_coverage()
    for field in (
        "candidate_eiu", "verified_eiu", "needs_review_eiu", "rejected_eiu",
        "claim_relation_summary", "document_audit",
    ):
        row[field] = current[field]
    return CoverageReportOut(**row)


@eiu_router.get("/gaps", response_model=GapListResponse)
def get_gaps() -> GapListResponse:
    gaps = compute_gaps()
    return GapListResponse(total=len(gaps), items=gaps)


# ----------------------------------------------------------------------
# EIU 详情 / 编辑 / 删除（全局路由）
# ----------------------------------------------------------------------
@eiu_router.post("/merge", response_model=EiuOut, status_code=201)
def merge_eius(payload: EiuMergeRequest) -> EiuOut:
    for source_eiu_id in payload.source_eiu_ids:
        source = database.get_eiu(source_eiu_id)
        if source is not None and source.get("auto_disposition") == "red":
            raise HTTPException(status_code=409, detail="已排除知识点仅可查看，不能合并")
    try:
        item = database.merge_eius(
            source_eiu_ids=payload.source_eiu_ids,
            statement=payload.statement,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="one or more EIU not found")
    database.save_audit(
        operation="merge",
        target_type="eiu",
        target_id=str(item["eiu_id"]),
        actor="api",
        detail={"source_eiu_ids": payload.source_eiu_ids},
    )
    return EiuOut(**item)


@eiu_router.post("/{eiu_id}/split", response_model=EiuListResponse, status_code=201)
def split_eiu(eiu_id: int, payload: EiuSplitRequest) -> EiuListResponse:
    source = database.get_eiu(eiu_id)
    if source is not None and source.get("auto_disposition") == "red":
        raise HTTPException(status_code=409, detail="已排除知识点仅可查看，不能拆分")
    try:
        items = database.split_eiu(source_eiu_id=eiu_id, statements=payload.statements)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if items is None:
        raise HTTPException(status_code=404, detail="eiu not found")
    database.save_audit(
        operation="split",
        target_type="eiu",
        target_id=str(eiu_id),
        actor="api",
        detail={"result_eiu_ids": [item["eiu_id"] for item in items]},
    )
    return EiuListResponse(total=len(items), items=items)


@eiu_router.get("/document/{document_id}/relationships")
def get_document_claim_relationships(document_id: int) -> dict:
    """返回文档内的只读关系建议；不触发自动合并或状态修改。"""
    if database.find_document_by_id(document_id) is None:
        raise HTTPException(status_code=404, detail="document not found")
    return analyse_claim_relationships(database.list_eius(document_id=document_id))


@eiu_router.get("/document/{document_id}/quality-feedback")
def get_document_quality_feedback(document_id: int) -> dict:
    """返回文档质量问题及可追溯 Block，不返回总分，也不要求人工确认。"""
    if database.find_document_by_id(document_id) is None:
        raise HTTPException(status_code=404, detail="document not found")
    return database.get_document_quality_feedback(document_id=document_id)


@eiu_router.get("/{eiu_id}", response_model=EiuDetail)
def get_eiu(eiu_id: int) -> EiuDetail:
    item = database.get_eiu(eiu_id)
    if item is None:
        raise HTTPException(status_code=404, detail="eiu not found")
    return EiuDetail(**item)


@eiu_router.put("/{eiu_id}", response_model=EiuOut)
def update_eiu(eiu_id: int, payload: EiuUpdate) -> EiuOut:
    current = database.get_eiu(eiu_id)
    if current is None:
        raise HTTPException(status_code=404, detail="eiu not found")
    if current.get("auto_disposition") == "red":
        raise HTTPException(status_code=409, detail="已排除知识点仅可查看，不能编辑")
    updates: dict = {}
    if payload.statement is not None:
        updates["statement"] = payload.statement
        updates["review_status"] = "candidate"
    if payload.eiu_type is not None:
        if payload.eiu_type not in EIU_TYPES:
            raise HTTPException(status_code=422, detail=f"非法 EIU 类型: {payload.eiu_type}")
        updates["eiu_type"] = payload.eiu_type
    if payload.content_priority is not None:
        raise HTTPException(status_code=422, detail="重要性由系统按全文重新判定，不能人工直接修改")
    if payload.is_questionable is not None:
        raise HTTPException(status_code=422, detail="请使用删除操作归档；可出题状态由自动质量门禁决定")
    if payload.exclusion_reason is not None:
        updates["exclusion_reason"] = payload.exclusion_reason
    if payload.constraints is not None:
        updates["constraints_json"] = payload.constraints
    if payload.subject is not None:
        updates["subject"] = payload.subject
    if payload.predicate is not None:
        updates["predicate"] = payload.predicate
    if payload.object is not None:
        updates["object_text"] = payload.object
    if payload.modality is not None:
        updates["modality"] = payload.modality
    if payload.qualifiers is not None:
        updates["qualifiers_json"] = payload.qualifiers
    if payload.extraction_confidence is not None:
        updates["extraction_confidence"] = payload.extraction_confidence
    if payload.quality_status is not None:
        raise HTTPException(status_code=422, detail="质量状态由三项自动门禁重新计算，不能人工直接修改")

    database.update_eiu(eiu_id, **updates)
    item = _recheck_document_gate(document_id=int(current["document_id"]), edited_eiu_id=eiu_id)
    database.save_audit(
        operation="update",
        target_type="eiu",
        target_id=str(eiu_id),
        actor="api",
        detail={"fields": sorted(updates)},
    )
    return EiuOut(**item)


@eiu_router.post("/{eiu_id}/manual-include", response_model=EiuOut)
def manual_include_eiu(eiu_id: int, payload: EiuManualIncludeRequest) -> EiuOut:
    """保留人工指定出题入口，但不覆盖自动质量、重要性或正式覆盖口径。"""
    current = database.get_eiu(eiu_id)
    if current is None:
        raise HTTPException(status_code=404, detail="eiu not found")
    if current.get("auto_disposition") == "red":
        raise HTTPException(status_code=409, detail="已排除知识点不可人工指定纳入")
    rechecked = _recheck_document_gate(document_id=int(current["document_id"]), edited_eiu_id=eiu_id)
    if rechecked.get("auto_disposition") not in {"green", "yellow"}:
        raise HTTPException(status_code=422, detail="知识点未通过重新核验，不能指定纳入")
    item = database.update_eiu(
        eiu_id,
        manual_include=True,
        manual_include_reason=payload.reason,
    )
    database.save_audit(
        operation="manual_include",
        target_type="eiu",
        target_id=str(eiu_id),
        actor="api",
        detail={"reason": payload.reason},
    )
    return EiuOut(**item)


@eiu_router.delete("/{eiu_id}", response_model=DeleteResponse)
def delete_eiu(eiu_id: int) -> DeleteResponse:
    current = database.get_eiu(eiu_id)
    if current is None:
        raise HTTPException(status_code=404, detail="eiu not found")
    if current.get("auto_disposition") == "red":
        raise HTTPException(status_code=409, detail="已排除知识点仅可查看")
    item = database.archive_eiu(eiu_id=eiu_id, reason="人工从待处理/可用知识点中归档排除")
    if item is None:
        raise HTTPException(status_code=404, detail="eiu not found")
    database.save_audit(
        operation="delete",
        target_type="eiu",
        target_id=str(eiu_id),
        actor="api",
        detail={"auto_disposition": "red", "reason": "manual_archive"},
    )
    return DeleteResponse(eiu_id=eiu_id, status="archived", review_status=item["review_status"])
