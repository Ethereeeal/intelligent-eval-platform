"""公共评测集库（BRD §8.22 FR-DS-SRC-004）。

组织方预置导入；条目同样经过质量评估与治理审核、版本化（新增/更新/停用留痕）；
用户只可查看和选择使用，不开放共享入库。
"""
from __future__ import annotations

from modules.m05_dataset_lifecycle.services.uploaded_set import assess_quality, validate_cases
from modules.shared.services.database import DatabaseService


def import_public_set(
    *,
    db: DatabaseService,
    name: str,
    version: str,
    dimensions: list[str] | None,
    cases: list[dict],
) -> dict:
    """预置导入公共评测集：字段校验（单轮 q/a）+ 质量评估 + 入库。"""
    errors = validate_cases(cases, "single")
    if errors:
        raise ValueError("；".join(errors))
    set_id = db.save_public_set(
        name=name,
        version=version,
        dimensions=dimensions,
        review_status="governance_passed",
    )
    db.save_public_cases(set_id=set_id, cases=cases)
    quality = assess_quality(cases)
    db.update_public_set(set_id, quality_snapshot=quality)
    return {"set_id": set_id, "quality": quality, "total_cases": len(cases)}
