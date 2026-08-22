from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from modules.m05_dataset_lifecycle.services.composition import (
    create_composition,
    resolve_composition,
)
from modules.m05_dataset_lifecycle.services.lifecycle import DatasetLifecycleService
from modules.m05_dataset_lifecycle.services.public_set import import_public_set
from modules.m05_dataset_lifecycle.services.uploaded_set import import_uploaded_set
from modules.shared.services.database import DatabaseService

router = APIRouter(prefix="/api", tags=["m05-dataset-lifecycle"])

_service = DatasetLifecycleService(DatabaseService())


# ----------------------------------------------------------------------
# 三类来源请求模型（BRD §8.22）
# ----------------------------------------------------------------------
class UploadedSetRequest(BaseModel):
    name: str
    template_type: str = "single"
    dimension: str | None = None
    source_file: str | None = None
    cases: list[dict]


class PublicSetRequest(BaseModel):
    name: str
    version: str = "v1.0.0"
    dimensions: list[str] | None = None
    cases: list[dict]


class PublicSetUpdate(BaseModel):
    name: str | None = None
    version: str | None = None
    dimensions: list[str] | None = None
    status: str | None = None


class CompositionRequest(BaseModel):
    name: str
    items: list[dict]
    created_by: str | None = None


class DimensionCreate(BaseModel):
    code: str
    name: str
    description: str | None = None


# 单次上传评测集样本数量上限（防超大 JSON 请求体）
_MAX_UPLOAD_CASES = 100_000


# ----------------------------------------------------------------------
# 版本
# ----------------------------------------------------------------------
@router.post("/freeze")
def freeze_version(
    created_by: str | None = None,
    document_ids: list[int] | None = Query(default=None, description="按选择合并：仅冻结所选文档的可发布评测项，并在合并时精确去重。"),
):
    try:
        return _service.freeze_version(created_by=created_by, document_ids=document_ids)
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
    try:
        result = _service.edit_case(case_id, **payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="case not found")
    return result


@router.delete("/cases/{case_id}")
def delete_case(case_id: int):
    try:
        deleted = _service.delete_case(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
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
        raise HTTPException(status_code=501, detail="xlsx export is not available in this demo")
    raise HTTPException(status_code=400, detail="unsupported format (jsonl|json|xlsx)")


# ----------------------------------------------------------------------
# 评测集管理：三类来源统一（BRD §8.22）
# ----------------------------------------------------------------------
@router.post("/eval-sets/upload")
def upload_eval_set(payload: UploadedSetRequest):
    """上传评测集（单轮/多轮）：格式校验 + 质量评估 + 入库（quality_checked）。"""
    if len(payload.cases) > _MAX_UPLOAD_CASES:
        raise HTTPException(
            status_code=400,
            detail=f"单次上传样本数 {len(payload.cases)} 超过上限 {_MAX_UPLOAD_CASES}",
        )
    try:
        result = import_uploaded_set(
            db=_service.db,
            name=payload.name,
            template_type=payload.template_type,
            dimension=payload.dimension,
            source_file=payload.source_file,
            cases=payload.cases,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        _service.db.save_audit(
            operation="eval_set.upload",
            target_type="uploaded_eval_set",
            target_id=str(result["set_id"]),
            actor="web",
            detail={"name": payload.name, "template_type": payload.template_type},
        )
    except Exception:  # noqa: BLE001 — 审计失败不阻断
        pass
    return result


@router.get("/eval-sets/uploaded")
def list_uploaded_sets():
    return _service.db.list_uploaded_sets()


@router.get("/eval-sets/uploaded/{set_id}")
def get_uploaded_set(set_id: int):
    item = _service.db.get_uploaded_set(set_id)
    if item is None:
        raise HTTPException(status_code=404, detail="uploaded eval set not found")
    return {"set": item, "cases": _service.db.list_uploaded_cases(set_id)}


@router.delete("/eval-sets/uploaded/{set_id}")
def delete_uploaded_set(set_id: int):
    if _service.db.get_uploaded_set(set_id) is None:
        raise HTTPException(status_code=404, detail="uploaded eval set not found")
    _service.db.delete_uploaded_set(set_id)
    try:
        _service.db.save_audit(
            operation="eval_set.delete",
            target_type="uploaded_eval_set",
            target_id=str(set_id),
            actor="web",
        )
    except Exception:  # noqa: BLE001
        pass
    return {"set_id": set_id, "deleted": True}


@router.post("/public-sets")
def import_public(payload: PublicSetRequest):
    """公共评测集库预置导入（组织方）。"""
    if len(payload.cases) > _MAX_UPLOAD_CASES:
        raise HTTPException(
            status_code=400,
            detail=f"单次导入样本数 {len(payload.cases)} 超过上限 {_MAX_UPLOAD_CASES}",
        )
    try:
        result = import_public_set(
            db=_service.db,
            name=payload.name,
            version=payload.version,
            dimensions=payload.dimensions,
            cases=payload.cases,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        _service.db.save_audit(
            operation="public_set.import",
            target_type="public_eval_set",
            target_id=str(result["set_id"]),
            actor="web",
            detail={"name": payload.name, "version": payload.version},
        )
    except Exception:  # noqa: BLE001
        pass
    return result


@router.get("/public-sets")
def list_public_sets(include_retired: bool = False):
    return _service.db.list_public_sets(include_retired=include_retired)


@router.get("/public-sets/{set_id}")
def get_public_set(set_id: int):
    item = _service.db.get_public_set(set_id)
    if item is None:
        raise HTTPException(status_code=404, detail="public eval set not found")
    return {"set": item, "cases": _service.db.list_public_cases(set_id)}


@router.put("/public-sets/{set_id}")
def update_public_set(set_id: int, payload: PublicSetUpdate):
    """更新公共库条目（版本化，更新/停用留痕）。"""
    if _service.db.get_public_set(set_id) is None:
        raise HTTPException(status_code=404, detail="public eval set not found")
    updates = payload.model_dump(exclude_none=True)
    item = _service.db.update_public_set(set_id, **updates)
    try:
        _service.db.save_audit(
            operation="public_set.update",
            target_type="public_eval_set",
            target_id=str(set_id),
            actor="web",
            detail=updates,
        )
    except Exception:  # noqa: BLE001
        pass
    return item


@router.delete("/public-sets/{set_id}")
def retire_public_set(set_id: int):
    """停用公共库条目（status=retired，保留版本历史）。"""
    if _service.db.get_public_set(set_id) is None:
        raise HTTPException(status_code=404, detail="public eval set not found")
    item = _service.db.update_public_set(set_id, status="retired")
    try:
        _service.db.save_audit(
            operation="public_set.retire",
            target_type="public_eval_set",
            target_id=str(set_id),
            actor="web",
        )
    except Exception:  # noqa: BLE001
        pass
    return item


@router.get("/dimensions")
def list_dimensions():
    return _service.db.list_dimensions()


@router.post("/dimensions")
def create_dimension(payload: DimensionCreate):
    """新增评测维度（可配置体系）。"""
    code = payload.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="维度 code 不能为空")
    dimension_id = _service.db.save_dimension(
        code=code, name=payload.name.strip(), description=payload.description
    )
    return {"dimension_id": dimension_id}


@router.post("/compositions")
def create_eval_composition(payload: CompositionRequest):
    """创建评测集组合（指定单个 / 勾选维度 / 多来源合并）。"""
    try:
        composition_id = create_composition(
            db=_service.db,
            name=payload.name,
            items=payload.items,
            created_by=payload.created_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"composition_id": composition_id}


@router.get("/compositions")
def list_compositions():
    return _service.db.list_compositions()


@router.get("/compositions/{composition_id}")
def get_composition(composition_id: int):
    composition = _service.db.get_composition(composition_id)
    if composition is None:
        raise HTTPException(status_code=404, detail="composition not found")
    return {"composition": composition, "samples": resolve_composition(_service.db, composition_id)}


@router.delete("/compositions/{composition_id}")
def delete_composition(composition_id: int):
    if _service.db.get_composition(composition_id) is None:
        raise HTTPException(status_code=404, detail="composition not found")
    _service.db.delete_composition(composition_id)
    try:
        _service.db.save_audit(
            operation="composition.delete",
            target_type="composition",
            target_id=str(composition_id),
            actor="web",
        )
    except Exception:  # noqa: BLE001
        pass
    return {"composition_id": composition_id, "deleted": True}
