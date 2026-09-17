"""M08 — Agent 评测 API（BRD §9）。

路由：
  POST /api/evaluation-runs                  发起批量运行（202，异步）
  GET  /api/evaluation-runs                  运行列表
  GET  /api/evaluation-runs/{id}             运行进度 + 汇总
  GET  /api/evaluation-runs/{id}/results     单题结果 + 分层指标汇总
  GET  /api/evaluation-runs/{id}/failures    E2E/D9 失败记录（ErrorBook）
  POST /api/evaluation-runs/{id}/cancel      取消运行（当前单题结束后生效）
  POST /api/evaluation-results/{id}/retry    单题复测（保留尝试链）
  PATCH /api/error-book/{id}                 人工处置异常项
  GET  /api/error-book                       智能体失败诊断与优化分析数据源
  GET  /api/adapters                         内置适配器清单
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from modules.m05_dataset_lifecycle.services.composition import resolve_composition
from modules.m08_auto_evaluation.schemas import (
    AdapterTestRequest,
    ContextAnalysisRequest,
    ErrorBookUpdateRequest,
    EvaluationCaseRetryRequest,
    EvaluationExportRequest,
    EvaluationRunRequest,
)
from modules.m08_auto_evaluation.services.adapter import (
    ADAPTER_REGISTRY,
    AdapterError,
    get_adapter,
)
from modules.m08_auto_evaluation.services.intermediate_metrics import normalize_intermediate_config
from modules.m08_auto_evaluation.services.judge import normalize_judge_config
from modules.m08_auto_evaluation.services.export import build_evaluation_workbook as _build_evaluation_workbook
from modules.m08_auto_evaluation.services.method_config import normalize_evaluation_selection
from modules.m08_auto_evaluation.services.metrics import aggregate
from modules.m08_auto_evaluation.services.optimization import cluster_error_book
from modules.m08_auto_evaluation.services.runner import start_case_retry_async, start_run_async
from modules.shared.services.database import DatabaseService

evaluation_router = APIRouter(prefix="/api", tags=["m08-auto-evaluation"])

_db = DatabaseService()

def _sanitize_adapter_config(config: dict | None) -> dict | None:
    """持久化前剔除敏感字段（API Key 不进库，避免经接口回显泄露）。"""
    if not config:
        return config
    sanitized = dict(config)
    sanitized.pop("api_key", None)
    # 通用 HTTP 模式的 Header 常携带 Token；运行记录只保留字段名，绝不落库其值。
    if isinstance(sanitized.get("headers"), dict):
        sanitized["headers"] = {key: "***" for key in sanitized["headers"]}
    return sanitized


def _validate_multi_turn_mode(samples: list[dict], multi_turn: bool) -> None:
    """保证前端选择的运行模式与组合内样本结构一致。"""
    has_turns = [
        isinstance(sample.get("turns"), list) and bool(sample.get("turns"))
        for sample in samples
    ]
    if multi_turn:
        missing_count = sum(not value for value in has_turns)
        if missing_count:
            raise ValueError(
                "已勾选多轮对话评测，但所选评测集存在 "
                f"{missing_count} 条样本缺少有效 turns"
            )
    elif any(has_turns):
        raise ValueError("所选评测集包含多轮样本，请勾选“多轮对话评测”后再发起")


@evaluation_router.post("/evaluation-runs", status_code=202)
def create_evaluation_run(payload: EvaluationRunRequest):
    """发起批量运行：组合解析为统一输入样本 → 异步线程逐题调用适配器。"""
    if _db.get_composition(payload.composition_id) is None:
        raise HTTPException(status_code=404, detail="composition not found")
    try:
        samples = resolve_composition(_db, payload.composition_id)
        _validate_multi_turn_mode(samples, payload.multi_turn)
        adapter = get_adapter(payload.adapter, payload.adapter_config)
        intermediate_config = normalize_intermediate_config(payload.intermediate_eval.model_dump())
        selection = normalize_evaluation_selection(
            payload.task_profile,
            payload.evaluation_methods,
            legacy_judge_enabled=payload.judge_eval.enabled,
        )
        judge_payload = payload.judge_eval.model_dump()
        judge_payload["enabled"] = "llm_as_judge" in selection["evaluation_methods"]
        judge_config = normalize_judge_config(judge_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AdapterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not samples:
        raise HTTPException(status_code=400, detail="组合解析为空，无可评测样本")
    if not selection["evaluation_methods"] and not intermediate_config["enabled"]:
        raise HTTPException(status_code=400, detail="至少选择一种评测方法或一个中间评测节点")
    run_id = _db.save_evaluation_run(
        composition_id=payload.composition_id,
        scenario_id=payload.scenario_id,
        dataset_version_id=payload.dataset_version_id,
        iteration_id=payload.iteration_id,
        agent_version=payload.agent_version,
        name=payload.name,
        adapter=payload.adapter,
        adapter_config=_sanitize_adapter_config(payload.adapter_config),
        intermediate_eval=intermediate_config,
        judge_eval=judge_config,
        task_profile=selection["task_profile"],
        evaluation_methods=selection["evaluation_methods"],
    )
    if payload.iteration_id is not None:
        _db.update_evaluation_iteration(
            payload.iteration_id,
            run_id=run_id,
            status="in_progress",
            agent_version=payload.agent_version,
        )
    start_run_async(
        run_id=run_id,
        samples=samples,
        adapter=adapter,
        intermediate_config=intermediate_config,
        judge_config=judge_config,
        evaluation_methods=selection["evaluation_methods"],
        task_profile=selection["task_profile"],
    )
    try:
        _db.save_audit(
            operation="evaluation_run.create",
            target_type="evaluation_run",
            target_id=str(run_id),
            actor="web",
            detail={
                "composition_id": payload.composition_id,
                "scenario_id": payload.scenario_id,
                "dataset_version_id": payload.dataset_version_id,
                "iteration_id": payload.iteration_id,
                "agent_version": payload.agent_version,
                "adapter": payload.adapter,
                "multi_turn": payload.multi_turn,
                "total": len(samples),
                "intermediate_eval": intermediate_config,
                "judge_eval": judge_config,
                "task_profile": selection["task_profile"],
                "evaluation_methods": selection["evaluation_methods"],
            },
        )
    except Exception:  # noqa: BLE001 — 审计失败不阻断
        pass
    return {"run_id": run_id, "status": "running", "total": len(samples)}


@evaluation_router.get("/evaluation-runs")
def list_evaluation_runs():
    return _db.list_evaluation_runs()


@evaluation_router.delete("/evaluation-runs/{run_id}")
def delete_evaluation_run(run_id: int, confirm: bool = Query(default=False)):
    """永久删除终态运行；必须显式二次确认，运行中任务应先取消。"""
    run = _get_run_or_404(run_id)
    if run.get("status") in {"pending", "running", "cancelling"}:
        raise HTTPException(status_code=409, detail="运行中任务不能删除，请先取消")
    if not confirm:
        raise HTTPException(status_code=400, detail="永久删除需要二次确认")
    deleted = _db.delete_evaluation_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    try:
        _db.save_audit(
            operation="evaluation_run.delete",
            target_type="evaluation_run",
            target_id=str(run_id),
            actor="web",
        )
    except Exception:  # noqa: BLE001 — 审计失败不阻断
        pass
    return {"ok": True, "run_id": run_id}


@evaluation_router.post("/evaluation-runs/{run_id}/cancel", status_code=202)
def cancel_evaluation_run(run_id: int):
    run = _get_run_or_404(run_id)
    if run.get("status") not in {"pending", "running", "cancelling"}:
        raise HTTPException(status_code=409, detail="当前运行已结束，不能取消")
    status = "cancelled" if run.get("status") == "pending" else "cancelling"
    updated = _db.update_evaluation_run(run_id, status=status)
    return {"run_id": run_id, "status": updated["status"]}


def _get_run_or_404(run_id: int) -> dict:
    run = _db.get_evaluation_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    return run


@evaluation_router.get("/evaluation-runs/{run_id}")
def get_evaluation_run(run_id: int):
    run = _get_run_or_404(run_id)
    results = _db.list_evaluation_results(run_id)
    return {
        "run": run,
        "summary": aggregate(
            results,
            run.get("intermediate_eval"),
            run.get("judge_eval"),
            run.get("task_profile"),
            run.get("evaluation_methods"),
        ),
    }


@evaluation_router.get("/evaluation-runs/{run_id}/results")
def evaluation_run_results(run_id: int):
    run = _get_run_or_404(run_id)
    results = _db.list_evaluation_results(run_id)
    issues = _db.list_error_book(run_id=run_id)
    by_result = {item.get("result_id"): item for item in issues if item.get("result_id")}
    by_case = {}
    for issue in issues:  # list_error_book 按新到旧排序，保留每道题最新处置记录
        if issue.get("case_uid"):
            by_case.setdefault(issue["case_uid"], issue)
    for item in results:
        item["error_book"] = by_result.get(item["result_id"]) or by_case.get(item.get("case_uid"))
    return {
        "results": results,
        "summary": aggregate(
            results,
            run.get("intermediate_eval"),
            run.get("judge_eval"),
            run.get("task_profile"),
            run.get("evaluation_methods"),
        ),
    }


@evaluation_router.get("/evaluation-results/{result_id}/attempts")
def evaluation_result_attempts(result_id: int):
    if _db.get_evaluation_result(result_id) is None:
        raise HTTPException(status_code=404, detail="evaluation result not found")
    return {"attempts": _db.list_evaluation_result_attempts(result_id)}


@evaluation_router.patch("/evaluation-results/{result_id}/context-analysis")
def update_context_analysis(result_id: int, payload: ContextAnalysisRequest):
    """保存失败/不确定多轮样本的上下文分析，不覆盖原始评分。"""
    result = _db.get_evaluation_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="evaluation result not found")
    if not result.get("turn_trace"):
        raise HTTPException(status_code=400, detail="该结果没有可分析的多轮请求上下文")
    if not payload.note.strip():
        raise HTTPException(status_code=400, detail="上下文分析备注不能为空")
    if result.get("status") == "passed" and (result.get("scores") or {}).get("score") is not None:
        raise HTTPException(status_code=400, detail="通过样本无需提交上下文错误分析")
    analysis = {
        "category": payload.category,
        "note": payload.note.strip(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    updated = _db.update_evaluation_case_result(result_id, context_analysis=analysis)
    issue = _db.get_error_book_item_for_result(
        result_id,
        run_id=result.get("run_id"),
        case_uid=result.get("case_uid"),
    )
    if issue:
        _db.update_error_book_item(
            issue["item_id"],
            root_cause=f"{payload.category}: {payload.note.strip()}",
        )
    return updated


@evaluation_router.post("/evaluation-results/{result_id}/retry", status_code=202)
def retry_evaluation_result(result_id: int, payload: EvaluationCaseRetryRequest):
    result = _db.get_evaluation_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="evaluation result not found")
    if result.get("parent_result_id") is not None:
        raise HTTPException(status_code=400, detail="请从原始结果发起复测")
    run = _get_run_or_404(result["run_id"])
    config = dict(run.get("adapter_config") or {})
    config.update(payload.adapter_config or {})
    try:
        adapter = get_adapter(run["adapter"], config)
    except (ValueError, AdapterError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    attempt_id = start_case_retry_async(
        run_id=run["run_id"],
        source_result=result,
        adapter=adapter,
        analysis_threshold=payload.analysis_threshold,
        intermediate_config=run.get("intermediate_eval"),
        judge_config=run.get("judge_eval"),
        evaluation_methods=run.get("evaluation_methods"),
        task_profile=run.get("task_profile") or "question_answering",
    )
    return {"result_id": result_id, "attempt_result_id": attempt_id, "status": "pending"}


@evaluation_router.post("/evaluation-runs/{run_id}/export")
def export_evaluation_run(run_id: int, payload: EvaluationExportRequest):
    run = _get_run_or_404(run_id)
    results = _db.list_evaluation_results(run_id)
    if payload.result_ids is not None:
        selected_ids = set(payload.result_ids)
        results = [item for item in results if item.get("result_id") in selected_ids]
    content = _build_evaluation_workbook(run, results)
    base_name = (run.get("name") or f"评测报告-{run_id}").replace("/", "-").replace("\\", "-")
    filename = f"{base_name}.xlsx"
    headers = {"Content-Disposition": f"attachment; filename=report-{run_id}.xlsx; filename*=UTF-8''{quote(filename)}"}
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@evaluation_router.get("/evaluation-runs/{run_id}/failures")
def evaluation_run_failures(run_id: int):
    _get_run_or_404(run_id)
    return _db.list_error_book(run_id=run_id)


@evaluation_router.post("/evaluation-runs/{run_id}/retry")
def retry_evaluation_run(run_id: int):
    """重跑（创建新 run，供同一冻结评测集复测比较，FR-OPT-002）。"""
    run = _get_run_or_404(run_id)
    if run.get("composition_id") is None:
        raise HTTPException(status_code=400, detail="原运行缺少组合，无法重跑")
    try:
        samples = resolve_composition(_db, run["composition_id"])
        adapter = get_adapter(run["adapter"], run.get("adapter_config"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AdapterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not samples:
        raise HTTPException(status_code=400, detail="组合解析为空，无可评测样本")
    new_run_id = _db.save_evaluation_run(
        composition_id=run["composition_id"],
        scenario_id=run.get("scenario_id"),
        dataset_version_id=run.get("dataset_version_id"),
        iteration_id=run.get("iteration_id"),
        agent_version=run.get("agent_version"),
        name=(run.get("name") or "评测运行") + "（重跑）",
        adapter=run["adapter"],
        adapter_config=_sanitize_adapter_config(run.get("adapter_config")),
        intermediate_eval=run.get("intermediate_eval"),
        judge_eval=run.get("judge_eval"),
        task_profile=run.get("task_profile") or "question_answering",
        evaluation_methods=run.get("evaluation_methods"),
    )
    if run.get("iteration_id") is not None:
        _db.update_evaluation_iteration(
            run["iteration_id"],
            run_id=new_run_id,
            status="in_progress",
        )
    start_run_async(
        run_id=new_run_id,
        samples=samples,
        adapter=adapter,
        intermediate_config=run.get("intermediate_eval"),
        judge_config=run.get("judge_eval"),
        evaluation_methods=run.get("evaluation_methods"),
        task_profile=run.get("task_profile") or "question_answering",
    )
    return {"run_id": new_run_id, "status": "running", "total": len(samples)}


@evaluation_router.get("/error-book")
def error_book(
    diagnosis: str | None = Query(default=None, description="按 E2E/D9 过滤"),
    status: str | None = Query(default=None, description="open/processed/verified/ignored"),
):
    items = _db.list_error_book(diagnosis=diagnosis, status=status)
    return {"items": items, "clusters": cluster_error_book(items)}


@evaluation_router.patch("/error-book/{item_id}")
def update_error_book(item_id: int, payload: ErrorBookUpdateRequest):
    if payload.status == "ignored" and not (payload.resolution_note or "").strip():
        raise HTTPException(status_code=400, detail="忽略异常时必须填写原因")
    if payload.status == "processed" and not (payload.resolution_category or "").strip():
        raise HTTPException(status_code=400, detail="标记已处理时必须选择人工分类")
    item = _db.update_error_book_item(
        item_id,
        status=payload.status,
        resolution_category=payload.resolution_category,
        resolution_note=payload.resolution_note,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="error book item not found")
    return item


@evaluation_router.post("/adapters/test")
def test_adapter(payload: AdapterTestRequest):
    try:
        adapter = get_adapter(payload.adapter, payload.adapter_config)
        result = adapter.run_single(payload.question)
    except (ValueError, AdapterError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.get("error"):
        raise HTTPException(status_code=502, detail=str(result["error"])[:300])
    return {
        "ok": True,
        "answer": result.get("answer"),
        "agent_observations": result.get("agent_observations"),
        "usage": result.get("usage") or {},
    }


@evaluation_router.get("/adapters")
def list_adapters():
    return [
        {
            "name": name,
            "description": (adapter_cls.__doc__ or "").strip(),
        }
        for name, adapter_cls in ADAPTER_REGISTRY.items()
    ]
