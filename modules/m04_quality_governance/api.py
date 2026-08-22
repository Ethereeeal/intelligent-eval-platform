"""m04 质量门禁：API 路由（薄壳，逻辑委托 PipelineService，按文件维度无 corpus）。

  POST /api/quality-check                      全量质量校验（或 ?document_id= 单文档）
  GET  /api/quality-check/results              校验结果汇总（只读）
  GET  /api/cases/{case_id}/quality-check      单题校验详情
  POST /api/cases/{case_id}/retry-check        单题重跑校验
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from modules.m04_quality_governance.schemas import (
    CaseQualityDetail,
    QualityCheckSummary,
    RetryCheckResult,
)
from modules.m04_quality_governance.services.pipeline import PipelineService

quality_router = APIRouter(prefix="/api", tags=["quality-governance"])

pipeline = PipelineService()


@quality_router.post(
    "/quality-check",
    response_model=QualityCheckSummary,
    summary="对待质检样本执行一轮质量校验（可按文档）",
)
def run_quality_check(document_id: int | None = Query(default=None, description="指定文档时仅校验该文档样本")):
    """仅遍历 candidate / needs_review 样本执行 5 项检查，并更新状态机。"""
    return pipeline.run_quality_check(document_id)


@quality_router.get(
    "/quality-check/results",
    response_model=QualityCheckSummary,
    summary="查询质量校验结果汇总",
)
def get_quality_results(document_id: int | None = Query(default=None, description="按文档过滤")):
    """基于已落库的检查结果生成汇总（不触发新一轮校验）。"""
    return pipeline.get_results_summary(document_id)


@quality_router.get(
    "/cases/{case_id}/quality-check",
    response_model=CaseQualityDetail,
    summary="查询单题质量校验详情",
)
def get_case_quality_check(case_id: int):
    detail = pipeline.get_case_checks(case_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="case not found")
    return detail


@quality_router.post(
    "/cases/{case_id}/retry-check",
    response_model=RetryCheckResult,
    summary="单题重跑质量校验",
)
def retry_case_quality_check(case_id: int):
    try:
        return pipeline.retry_check(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
