"""评测集组合选择（BRD §8.22 FR-DS-SRC-005）。

组合来源：doc_generated（冻结版本 eval_case）/ uploaded（上传评测集）/ public（公共库）；
可指定单个评测集、勾选公共库维度、多来源合并成临时标准化评测集；
组合结果作为评测运行配置记录并参与审计。
"""
from __future__ import annotations

from modules.shared.services.database import DatabaseService

VALID_SOURCES = {"doc_generated", "uploaded", "public"}


def validate_composition_items(items: list[dict], db: DatabaseService) -> list[str]:
    """组合项校验：source 合法、引用对象存在。"""
    errors: list[str] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"第 {idx} 项不是对象")
            continue
        source = item.get("source")
        if source not in VALID_SOURCES:
            errors.append(f"第 {idx} 项 source 非法: {source}（{sorted(VALID_SOURCES)}）")
            continue
        if source == "doc_generated":
            version = db.get_dataset_version(item.get("version_id"))
            if version is None:
                errors.append(f"第 {idx} 项 doc_generated 版本不存在: {item.get('version_id')}")
            elif version.get("status") != "frozen":
                errors.append(f"第 {idx} 项 doc_generated 必须引用 frozen 版本")
        elif source == "uploaded" and db.get_uploaded_set(item.get("set_id")) is None:
            errors.append(f"第 {idx} 项上传评测集不存在: {item.get('set_id')}")
        elif source == "public" and db.get_public_set(item.get("set_id")) is None:
            errors.append(f"第 {idx} 项公共评测集不存在: {item.get('set_id')}")
    return errors


def create_composition(
    *,
    db: DatabaseService,
    name: str,
    items: list[dict],
    created_by: str | None = None,
) -> int:
    """创建组合并审计（返回 composition_id）。"""
    errors = validate_composition_items(items, db)
    if errors:
        raise ValueError("；".join(errors[:20]))
    composition_id = db.save_composition(name=name, items=items, created_by=created_by)
    try:
        db.save_audit(
            operation="composition.create",
            target_type="composition",
            target_id=str(composition_id),
            actor=created_by or "web",
            detail={"name": name, "items": items},
        )
    except Exception:  # noqa: BLE001 — 审计失败不阻断
        pass
    return composition_id


def _eval_case_to_sample(case: dict, source: str) -> dict:
    return {
        "case_uid": f"doc_{case['case_id']}",
        "question": case.get("question") or "",
        "gold_answer": case.get("gold_answer"),
        "difficulty": case.get("difficulty"),
        "dimension": None,
        "source": source,
        "turns": None,
        "session_id": None,
    }


def resolve_composition(db: DatabaseService, composition_id: int) -> list[dict]:
    """把组合解析为统一运行输入样本列表（供 m08 EvaluationRun 消费）。"""
    composition = db.get_composition(composition_id)
    if composition is None:
        raise ValueError("composition not found")
    samples: list[dict] = []
    for item in composition.get("items") or []:
        source = item.get("source")
        if source == "doc_generated":
            version_id = item.get("version_id")
            version = db.get_dataset_version(version_id)
            if version is None or version.get("status") != "frozen":
                raise ValueError("doc_generated composition must reference a frozen version")
            cases = db.get_eval_cases(version_id, include_retired=False, limit=100000)
            samples.extend(_eval_case_to_sample(c, source) for c in cases)
        elif source == "uploaded":
            set_id = item.get("set_id")
            for case in db.list_uploaded_cases(set_id):
                samples.append(
                    {
                        "case_uid": f"up_{case['case_id']}",
                        "question": case.get("q") or "",
                        "gold_answer": case.get("a"),
                        "difficulty": None,
                        "dimension": case.get("dimension"),
                        "source": source,
                        "session_id": case.get("session_id"),
                        "turns": case.get("turns"),
                    }
                )
        elif source == "public":
            set_id = item.get("set_id")
            for case in db.list_public_cases(set_id):
                samples.append(
                    {
                        "case_uid": f"pub_{case['case_id']}",
                        "question": case.get("q") or "",
                        "gold_answer": case.get("a"),
                        "difficulty": None,
                        "dimension": case.get("dimension"),
                        "source": source,
                        "session_id": None,
                        "turns": None,
                    }
                )
    # 按组合项逐项过滤：item.dimension 非空时只保留该来源 + 该维度的样本；
    # 未指定维度时保留该来源全部样本（不整体替换其他来源的样本）。
    selected: list[dict] = []
    for item in composition.get("items") or []:
        dimension = item.get("dimension")
        source = item.get("source")
        for sample in samples:
            if sample["source"] == source and (
                not dimension or sample.get("dimension") == dimension
            ):
                selected.append(sample)
    # 按组合项过滤后的结果直接返回（所有项均未命中维度时返回空，不回退全量）
    return selected
