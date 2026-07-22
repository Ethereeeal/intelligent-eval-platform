"""Requirement document → test function points API routes."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter(prefix="/api/requirements")

# ---------------------------------------------------------------------------
# In-memory stub storage for Demo
# ---------------------------------------------------------------------------
_stub_requirements: list[dict] = []
_stub_tfps: list[dict] = []
_next_req_id = 1
_next_tfp_id = 1


@router.post("/upload")
async def upload_requirement(
    corpus_id: int = Form(...),
    file: UploadFile = File(...),
) -> dict:
    """Upload a business requirement document."""
    global _next_req_id
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容不能为空")

    req_doc = {
        "requirement_doc_id": _next_req_id,
        "corpus_id": corpus_id,
        "file_name": file.filename or "requirement_doc",
        "file_type": file.content_type or "application/octet-stream",
        "requirement_version": "1.0",
        "business_domain": None,
        "parse_status": "uploaded",
        "uploaded_at": datetime.utcnow().isoformat(),
    }
    _stub_requirements.append(req_doc)
    _next_req_id += 1

    return {
        "requirement_doc_id": req_doc["requirement_doc_id"],
        "file_name": req_doc["file_name"],
        "status": "uploaded",
        "message": "需求书已上传，可触发 EIU 提取。",
    }


@router.get("")
def list_requirements(corpus_id: int | None = None) -> list[dict]:
    """List requirement documents, optionally filtered by corpus."""
    if corpus_id is not None:
        return [r for r in _stub_requirements if r.get("corpus_id") == corpus_id]
    return _stub_requirements


@router.get("/{requirement_doc_id}")
def get_requirement(requirement_doc_id: int) -> dict:
    """Get a requirement document's metadata."""
    for r in _stub_requirements:
        if r["requirement_doc_id"] == requirement_doc_id:
            return r
    raise HTTPException(status_code=404, detail="需求书不存在")


@router.post("/{requirement_doc_id}/extract")
def extract_eiu(requirement_doc_id: int) -> dict:
    """Trigger EIU extraction → test function points.

    Demo: returns static example TFPs to demonstrate the data shape.
    """
    # Check requirement exists
    req = None
    for r in _stub_requirements:
        if r["requirement_doc_id"] == requirement_doc_id:
            req = r
            break
    if req is None:
        raise HTTPException(status_code=404, detail="需求书不存在")

    global _next_tfp_id

    # Generate demo test function points
    demo_tfps = [
        {
            "tfp_id": _next_tfp_id + i,
            "requirement_doc_id": requirement_doc_id,
            "section_path": f"3. 功能需求 > 3.{i+1} 示例模块",
            "requirement_id": f"FR-DEMO-{i+1:03d}",
            "statement": stmt,
            "eiu_type": eiu_type,
            "content_priority": prio,
            "weight": w,
            "evidence_range": [],
            "is_questionable": True,
            "exclusion_reason": None,
            "extraction_confidence": 0.92,
            "review_status": "candidate",
            "created_at": datetime.utcnow().isoformat(),
        }
        for i, (stmt, eiu_type, prio, w) in enumerate(
            [
                ("系统应支持用户通过用户名+密码方式登录，密码长度不少于8位且包含字母和数字", "functional_rule", "P0", 5),
                ("当用户连续5次输入错误密码时，账户应锁定30分钟", "business_rule", "P0", 5),
                ("用户名应为不少于3位且不超过32位的字母数字组合", "data_rule", "P1", 3),
                ("登录接口在99%的请求下应在2秒内返回响应", "nfr", "P1", 3),
            ]
        )
    ]

    _next_tfp_id += len(demo_tfps)
    _stub_tfps.extend(demo_tfps)

    # Update requirement status
    req["parse_status"] = "extracted"

    return {
        "requirement_doc_id": requirement_doc_id,
        "extracted_count": len(demo_tfps),
        "status": "extraction_complete",
        "message": f"已提取 {len(demo_tfps)} 个测试功能点（Demo 示例数据）。",
    }


@router.get("/{requirement_doc_id}/test-function-points")
def get_test_function_points(
    requirement_doc_id: int,
    priority: str | None = None,
) -> dict:
    """Get the test function points (EIU list) for a requirement document."""
    items = [t for t in _stub_tfps if t["requirement_doc_id"] == requirement_doc_id]
    if priority:
        items = [t for t in items if t["content_priority"] == priority]

    # Summary statistics
    summary = {
        "total": len(items),
        "by_priority": {},
        "by_type": {},
        "by_section": {},
    }
    for t in items:
        summary["by_priority"][t["content_priority"]] = summary["by_priority"].get(t["content_priority"], 0) + 1
        summary["by_type"][t["eiu_type"]] = summary["by_type"].get(t["eiu_type"], 0) + 1
        summary["by_section"][t["section_path"]] = summary["by_section"].get(t["section_path"], 0) + 1

    return {
        "requirement_doc_id": requirement_doc_id,
        "total_count": len(items),
        "items": items,
        "summary": summary,
    }


@router.get("/{requirement_doc_id}/export")
def export_test_function_points(requirement_doc_id: int, format: str = "json") -> dict:
    """Export test function points in the requested format.

    Supported formats: json, excel, markdown.
    Demo: always returns JSON structure; format param acknowledged in response metadata.
    """
    items = [t for t in _stub_tfps if t["requirement_doc_id"] == requirement_doc_id]
    return {
        "format": format,
        "exported_at": datetime.utcnow().isoformat(),
        "count": len(items),
        "data": items,
        "note": "Demo 阶段仅支持 JSON 格式导出。Excel/Markdown 导出将在后续实现。",
    }
