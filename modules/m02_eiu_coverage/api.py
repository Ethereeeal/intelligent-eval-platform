"""M02 — EIU 抽取与覆盖规划 API（SPEC §7）。

路由：
  POST   /api/corpus/{corpus_id}/eiu/extract  异步触发 EIU 抽取（返回 job_id）
  GET    /api/corpus/{corpus_id}/eiu           EIU 清单（支持过滤）
  GET    /api/corpus/{corpus_id}/eiu/coverage  覆盖率报告
  GET    /api/corpus/{corpus_id}/eiu/gaps      未覆盖 EIU 清单
  GET    /api/eiu/{eiu_id}                     EIU 详情（含原文上下文）
  PUT    /api/eiu/{eiu_id}                     手动编辑 EIU
  DELETE /api/eiu/{eiu_id}                     软删除（标记 blocked）
"""
from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException, Query

from modules.shared.services.database import EIU_TYPES, PRIORITY_WEIGHT, DatabaseService
from modules.m02_eiu_coverage.schemas import (
    CoverageReport,
    CoverageReportOut,
    DeleteResponse,
    EiuDetail,
    EiuExtractResponse,
    EiuListResponse,
    EiuOut,
    EiuUpdate,
    GapListResponse,
)
from modules.m02_eiu_coverage.services.coverage import (
    compute_coverage,
    compute_gaps,
    save_coverage_report,
)
from modules.m02_eiu_coverage.services.eiu_extractor import EiuExtractorService

# 绑定语料库：/api/corpus/{corpus_id}/eiu
corpus_eiu_router = APIRouter(prefix="/api/corpus/{corpus_id}/eiu", tags=["eiu"])
# 全局（不绑定语料库）：/api/eiu/...
eiu_router = APIRouter(prefix="/api/eiu", tags=["eiu"])

database = DatabaseService()
extractor_service = EiuExtractorService()


def _ensure_corpus(corpus_id: int) -> None:
    if database.get_corpus(corpus_id) is None:
        raise HTTPException(status_code=404, detail="corpus not found")


# ----------------------------------------------------------------------
# 异步抽取
# ----------------------------------------------------------------------
@corpus_eiu_router.post("/extract", response_model=EiuExtractResponse, status_code=202)
def trigger_eiu_extract(corpus_id: int) -> EiuExtractResponse:
    _ensure_corpus(corpus_id)

    job_id = database.save_job(corpus_id=corpus_id, document_id=0, job_type="eiu_extract")
    database.update_job(
        job_id, status="running", phase="queued", progress=0, message="任务已创建，准备抽取"
    )

    total = _count_paragraph_blocks(corpus_id)
    if total == 0:
        # 验收 F11：无 Block 时不报错，返回"无可处理的段落"
        database.update_job(
            job_id, status="completed", phase="done", progress=100,
            message="无可处理的段落", finished=True,
        )
        return EiuExtractResponse(
            job_id=job_id, corpus_id=corpus_id, status="completed", message="无可处理的段落"
        )

    database.update_job(job_id, progress=0, message=f"开始 EIU 抽取，共 {total} 个段落 Block")
    thread = threading.Thread(
        target=extractor_service.extract_corpus,
        kwargs={"corpus_id": corpus_id, "job_id": job_id},
        daemon=True,
    )
    thread.start()
    return EiuExtractResponse(
        job_id=job_id,
        corpus_id=corpus_id,
        status="running",
        message=f"开始 EIU 抽取，共 {total} 个段落 Block",
    )


def _count_paragraph_blocks(corpus_id: int) -> int:
    total = 0
    for document in database.list_documents(corpus_id):
        total += sum(
            1
            for block in database.get_document_blocks(document["document_id"])
            if block["block_type"] != "title"
        )
    return total


# ----------------------------------------------------------------------
# EIU 清单 / 覆盖率 / 未覆盖清单
# ----------------------------------------------------------------------
@corpus_eiu_router.get("", response_model=EiuListResponse)
def list_eius(
    corpus_id: int,
    type: list[str] | None = Query(None, description="EIU 类型，可重复（?type=rule&type=threshold）"),
    priority: list[str] | None = Query(None, description="优先级 P0/P1/P2，可重复"),
    questionable: bool | None = Query(None, description="是否可出题"),
    section: str | None = Query(None, description="按章节路径模糊过滤"),
    document_id: int | None = Query(None, description="按文档过滤"),
) -> EiuListResponse:
    _ensure_corpus(corpus_id)
    items = database.list_eius(
        corpus_id,
        eiu_type=type,
        priority=priority,
        questionable=questionable,
        section=section,
        document_id=document_id,
    )
    return EiuListResponse(corpus_id=corpus_id, total=len(items), items=items)


@corpus_eiu_router.get("/coverage", response_model=CoverageReport)
def get_coverage(corpus_id: int) -> CoverageReport:
    _ensure_corpus(corpus_id)
    # M02 阶段无题目（covered 为空）；M03 接入后可传入 covered_eiu_ids
    return CoverageReport(**compute_coverage(corpus_id))


@corpus_eiu_router.post("/coverage", response_model=CoverageReportOut, status_code=201)
def persist_coverage(corpus_id: int) -> CoverageReportOut:
    """计算覆盖率并落库为 coverage_report，返回带 report_id 的报告（供 m05 冻结外键引用）。"""
    _ensure_corpus(corpus_id)
    report_id = save_coverage_report(corpus_id)
    row = database.get_latest_coverage_report(corpus_id)
    return CoverageReportOut(**row)


@corpus_eiu_router.get("/gaps", response_model=GapListResponse)
def get_gaps(corpus_id: int) -> GapListResponse:
    _ensure_corpus(corpus_id)
    gaps = compute_gaps(corpus_id)
    return GapListResponse(corpus_id=corpus_id, total=len(gaps), items=gaps)


# ----------------------------------------------------------------------
# EIU 详情 / 编辑 / 删除（全局路由）
# ----------------------------------------------------------------------
@eiu_router.get("/{eiu_id}", response_model=EiuDetail)
def get_eiu(eiu_id: int) -> EiuDetail:
    item = database.get_eiu(eiu_id)
    if item is None:
        raise HTTPException(status_code=404, detail="eiu not found")
    return EiuDetail(**item)


@eiu_router.put("/{eiu_id}", response_model=EiuOut)
def update_eiu(eiu_id: int, payload: EiuUpdate) -> EiuOut:
    updates: dict = {}
    if payload.statement is not None:
        updates["statement"] = payload.statement
    if payload.eiu_type is not None:
        if payload.eiu_type not in EIU_TYPES:
            raise HTTPException(status_code=422, detail=f"非法 EIU 类型: {payload.eiu_type}")
        updates["eiu_type"] = payload.eiu_type
    if payload.content_priority is not None:
        if payload.content_priority not in PRIORITY_WEIGHT:
            raise HTTPException(status_code=422, detail=f"非法优先级: {payload.content_priority}")
        updates["content_priority"] = payload.content_priority
        updates["weight"] = PRIORITY_WEIGHT[payload.content_priority]
    if payload.is_questionable is not None:
        updates["is_questionable"] = payload.is_questionable
        if payload.is_questionable:
            updates["exclusion_reason"] = None
    if payload.exclusion_reason is not None:
        updates["exclusion_reason"] = payload.exclusion_reason
    if payload.constraints is not None:
        updates["constraints_json"] = payload.constraints
    if payload.extraction_confidence is not None:
        updates["extraction_confidence"] = payload.extraction_confidence

    item = database.update_eiu(eiu_id, **updates)
    if item is None:
        raise HTTPException(status_code=404, detail="eiu not found")
    return EiuOut(**item)


@eiu_router.delete("/{eiu_id}", response_model=DeleteResponse)
def delete_eiu(eiu_id: int) -> DeleteResponse:
    item = database.mark_eiu_blocked(eiu_id)
    if item is None:
        raise HTTPException(status_code=404, detail="eiu not found")
    return DeleteResponse(eiu_id=eiu_id, status="deleted", review_status="blocked")
