"""M08 — Agent 评测 API（BRD §9）。

路由：
  POST /api/evaluation-runs                  发起批量运行（202，异步）
  GET  /api/evaluation-runs                  运行列表
  GET  /api/evaluation-runs/{id}             运行进度 + 汇总
  GET  /api/evaluation-runs/{id}/results     单题结果 + 分层指标汇总
  GET  /api/evaluation-runs/{id}/failures    E2E/D9 失败记录（ErrorBook）
  POST /api/evaluation-runs/{id}/retry       重跑（新 run，供回归比较）
  GET  /api/error-book                       智能体失败诊断与优化分析数据源
  GET  /api/adapters                         内置适配器清单
"""
from __future__ import annotations

from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from modules.m05_dataset_lifecycle.services.composition import resolve_composition
from modules.m08_auto_evaluation.schemas import EvaluationExportRequest, EvaluationRunRequest
from modules.m08_auto_evaluation.services.adapter import (
    ADAPTER_REGISTRY,
    AdapterError,
    get_adapter,
)
from modules.m08_auto_evaluation.services.metrics import aggregate
from modules.m08_auto_evaluation.services.optimization import cluster_error_book
from modules.m08_auto_evaluation.services.runner import start_run_async
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


@evaluation_router.post("/evaluation-runs", status_code=202)
def create_evaluation_run(payload: EvaluationRunRequest):
    """发起批量运行：组合解析为统一输入样本 → 异步线程逐题调用适配器。"""
    if _db.get_composition(payload.composition_id) is None:
        raise HTTPException(status_code=404, detail="composition not found")
    try:
        samples = resolve_composition(_db, payload.composition_id)
        adapter = get_adapter(payload.adapter, payload.adapter_config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AdapterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not samples:
        raise HTTPException(status_code=400, detail="组合解析为空，无可评测样本")
    run_id = _db.save_evaluation_run(
        composition_id=payload.composition_id,
        name=payload.name,
        adapter=payload.adapter,
        adapter_config=_sanitize_adapter_config(payload.adapter_config),
    )
    start_run_async(run_id=run_id, samples=samples, adapter=adapter)
    try:
        _db.save_audit(
            operation="evaluation_run.create",
            target_type="evaluation_run",
            target_id=str(run_id),
            actor="web",
            detail={
                "composition_id": payload.composition_id,
                "adapter": payload.adapter,
                "total": len(samples),
            },
        )
    except Exception:  # noqa: BLE001 — 审计失败不阻断
        pass
    return {"run_id": run_id, "status": "running", "total": len(samples)}


@evaluation_router.get("/evaluation-runs")
def list_evaluation_runs():
    return _db.list_evaluation_runs()


def _get_run_or_404(run_id: int) -> dict:
    run = _db.get_evaluation_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    return run


@evaluation_router.get("/evaluation-runs/{run_id}")
def get_evaluation_run(run_id: int):
    run = _get_run_or_404(run_id)
    results = _db.list_evaluation_results(run_id)
    return {"run": run, "summary": aggregate(results)}


@evaluation_router.get("/evaluation-runs/{run_id}/results")
def evaluation_run_results(run_id: int):
    _get_run_or_404(run_id)
    results = _db.list_evaluation_results(run_id)
    return {"results": results, "summary": aggregate(results)}


def _build_evaluation_workbook(run: dict, results: list[dict]) -> bytes:
    """生成便于测试人员筛选和归因的 Excel 原始报告。"""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "原始评测报告"
    headers = [
        "序号", "问题", "标准答案", "智能体回答", "得分", "状态", "耗时(ms)",
        "维度", "难度", "来源", "归因", "错误信息", "用例ID",
    ]
    sheet.append(headers)
    header_fill = PatternFill("solid", fgColor="6750A4")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for index, item in enumerate(results, start=1):
        scores = item.get("scores") or {}
        sheet.append([
            index,
            item.get("question") or "",
            item.get("gold_answer") or "",
            item.get("answer") or "",
            scores.get("score"),
            item.get("status") or "",
            scores.get("latency_ms"),
            item.get("dimension") or "",
            item.get("difficulty") or "",
            item.get("source") or "",
            item.get("diagnosis") or "",
            item.get("error_message") or "",
            item.get("case_uid") or "",
        ])
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    widths = [8, 42, 42, 42, 10, 12, 12, 16, 12, 16, 16, 32, 24]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.row_dimensions[1].height = 24

    summary = workbook.create_sheet("运行摘要")
    composition_id = run.get("composition_id")
    summary_rows = [
        ("运行名称", run.get("name") or f"运行 #{run.get('run_id')}"),
        ("运行ID", run.get("run_id")),
        ("可执行评测集版本", f"#{composition_id}" if composition_id is not None else "—"),
        ("适配器", run.get("adapter") or ""),
        ("状态", run.get("status") or ""),
        ("结果数量", len(results)),
        ("创建时间", run.get("created_at") or ""),
        ("开始时间", run.get("started_at") or ""),
        ("完成时间", run.get("finished_at") or ""),
    ]
    for key, value in summary_rows:
        summary.append([key, value])
    summary.column_dimensions["A"].width = 22
    summary.column_dimensions["B"].width = 48
    for cell in summary[1]:
        cell.font = Font(bold=True)

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


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
        name=(run.get("name") or "评测运行") + "（重跑）",
        adapter=run["adapter"],
        adapter_config=_sanitize_adapter_config(run.get("adapter_config")),
    )
    start_run_async(run_id=new_run_id, samples=samples, adapter=adapter)
    return {"run_id": new_run_id, "status": "running", "total": len(samples)}


@evaluation_router.get("/error-book")
def error_book(
    diagnosis: str | None = Query(default=None, description="按 E2E/D9 过滤"),
    status: str | None = Query(default=None, description="open/fixed/closed"),
):
    items = _db.list_error_book(diagnosis=diagnosis, status=status)
    return {"items": items, "clusters": cluster_error_book(items)}


@evaluation_router.get("/adapters")
def list_adapters():
    return [
        {
            "name": name,
            "description": (adapter_cls.__doc__ or "").strip(),
        }
        for name, adapter_cls in ADAPTER_REGISTRY.items()
    ]
