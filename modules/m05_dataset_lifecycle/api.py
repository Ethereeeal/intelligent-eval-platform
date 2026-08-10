from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from modules.m05_dataset_lifecycle.services.lifecycle import DatasetLifecycleService
from modules.shared.services.database import DatabaseService

router = APIRouter(prefix="/api", tags=["m05-dataset-lifecycle"])

_service = DatasetLifecycleService(DatabaseService())


# ----------------------------------------------------------------------
# 版本
# ----------------------------------------------------------------------
@router.post("/freeze")
def freeze_version(created_by: str | None = None):
    try:
        return _service.freeze_version(created_by=created_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/versions")
def list_versions():
    return _service.list_versions()


@router.get("/versions/{version_id}")
def get_version(version_id: int):
    version = _service.get_version(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="version not found")
    return version


# ----------------------------------------------------------------------
# 编辑 / 删除
# ----------------------------------------------------------------------
@router.put("/cases/{case_id}")
def edit_case(case_id: int, payload: dict):
    result = _service.edit_case(case_id, **payload)
    if result is None:
        raise HTTPException(status_code=404, detail="case not found")
    return result


@router.delete("/cases/{case_id}")
def delete_case(case_id: int):
    if not _service.delete_case(case_id):
        raise HTTPException(status_code=404, detail="case not found")
    return {"ok": True}


# ----------------------------------------------------------------------
# 表格视图 / 统计
# ----------------------------------------------------------------------
@router.get("/versions/{version_id}/cases")
def list_cases(
    version_id: int,
    include_retired: bool = False,
    source: str | None = Query(None, pattern="^(native|augmentation)$"),
    limit: int = 200,
    offset: int = 0,
):
    return _service.list_cases(
        version_id, include_retired=include_retired, source=source, limit=limit, offset=offset
    )


@router.get("/versions/{version_id}/stats")
def case_stats(version_id: int):
    return _service.case_stats(version_id)


# ----------------------------------------------------------------------
# 树形浏览
# ----------------------------------------------------------------------
@router.get("/tree")
def tree():
    return _service.tree()


# ----------------------------------------------------------------------
# 导出
# ----------------------------------------------------------------------
@router.get("/versions/{version_id}/export")
def export_version(version_id: int, format: str = "jsonl"):
    if format == "jsonl":
        return Response(_service.export_jsonl(version_id), media_type="application/x-ndjson")
    if format == "json":
        return _service.export_json(version_id)
    if format == "xlsx":
        return Response(
            _service.export_xlsx(version_id),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=dataset.csv"},
        )
    raise HTTPException(status_code=400, detail="unsupported format (jsonl|json|xlsx)")
