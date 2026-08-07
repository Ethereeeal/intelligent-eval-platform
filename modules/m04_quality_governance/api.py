"""m04 质量门禁：API 路由（薄壳，逻辑委托 PipelineService）。

对应 README §4 API 清单：
  POST /api/corpus/{corpus_id}/quality-check          全量质量校验
  GET  /api/corpus/{corpus_id}/quality-check/results  校验结果汇总（只读）
  GET  /api/cases/{case_id}/quality-check             单题校验详情
  POST /api/cases/{case_id}/retry-check               单题重跑校验
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from modules.m04_quality_governance.schemas import (
    CaseQualityDetail,
    QualityCheckSummary,
    RetryCheckResult,
)
from modules.m04_quality_governance.services.pipeline import PipelineService

quality_router = APIRouter(prefix="/api", tags=["quality-governance"])

pipeline = PipelineService()


@quality_router.post(
    "/corpus/{corpus_id}/quality-check",
    response_model=QualityCheckSummary,
    summary="对语料库全部样本执行一轮质量校验",
)
def run_quality_check(corpus_id: int):
    """遍历 corpus 下全部候选样本执行 5 项检查，并更新各 case 状态机。"""
    return pipeline.run_quality_check(corpus_id)


@quality_router.get(
    "/corpus/{corpus_id}/quality-check/results",
    response_model=QualityCheckSummary,
    summary="查询语料库质量校验结果汇总",
)
def get_quality_results(corpus_id: int):
    """基于已落库的检查结果生成汇总（不触发新一轮校验）。"""
    return pipeline.get_results_summary(corpus_id)


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
