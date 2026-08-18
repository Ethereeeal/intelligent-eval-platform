"""上传评测集（BRD §8.22 FR-DS-SRC-001/002/003/006）。

流程：模板字段校验（单轮 q/a/evidence/dimension；多轮 session_id+turns[]）
→ 质量评估（数据完整率 / 重复问题比例 / 有效 QA 比例 / 覆盖维度）
→ 入库状态机（pending → quality_checked → governance_passed → published）。
"""
from __future__ import annotations

from modules.m05_dataset_lifecycle.services.scoring import normalize_answer
from modules.shared.services.database import DatabaseService

_MAX_ERRORS = 20


def validate_cases(cases: list[dict], template_type: str) -> list[str]:
    """模板字段校验，返回错误列表（空 = 通过）。"""
    errors: list[str] = []
    if not cases:
        return ["评测集为空，至少需要一条样本"]
    for idx, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            errors.append(f"第 {idx} 条不是对象")
            continue
        if template_type == "single":
            for field in ("q", "a"):
                if not str(case.get(field) or "").strip():
                    errors.append(f"第 {idx} 条缺少必填字段 {field}")
        else:  # multi
            if not str(case.get("session_id") or "").strip():
                errors.append(f"第 {idx} 条多轮样本缺少 session_id")
            turns = case.get("turns") or []
            if not turns:
                errors.append(f"第 {idx} 条多轮样本 turns 为空")
            else:
                last = turns[-1]
                if isinstance(last, dict) and not str(last.get("a") or "").strip():
                    errors.append(f"第 {idx} 条最终轮缺少标准答案 a")
                for turn_idx, turn in enumerate(turns, start=1):
                    if not isinstance(turn, dict):
                        continue
                    if turn.get("key_turn") and (
                        turn.get("turn_type") not in ("memory", "coherence")
                        or not turn.get("depends_on_turns")
                    ):
                        errors.append(
                            f"第 {idx} 条第 {turn_idx} 轮 key_turn 必须为 memory/coherence 且声明 depends_on_turns"
                        )
        if len(errors) >= _MAX_ERRORS:
            errors.append("（错误过多，已截断）")
            break
    return errors


def assess_quality(cases: list[dict]) -> dict:
    """上传评测集质量评估（BRD FR-QA-005：数据完整率/重复问题比例/有效QA比例/覆盖维度）。"""
    total = len(cases)
    complete = sum(
        1
        for c in cases
        if str(c.get("q") or "").strip() and str(c.get("a") or "").strip()
    )
    valid_qa = sum(
        1
        for c in cases
        if str(c.get("q") or "").strip() and len(str(c.get("q") or "").strip()) >= 2
        and str(c.get("a") or "").strip()
    )
    seen: set[str] = set()
    duplicate = 0
    for c in cases:
        key = normalize_answer(str(c.get("q") or ""))
        if not key:
            continue
        if key in seen:
            duplicate += 1
        else:
            seen.add(key)
    dimensions = sorted(
        {str(c.get("dimension")).strip() for c in cases if c.get("dimension")}
    )
    return {
        "data_completeness_rate": round(complete / total, 4) if total else 0.0,
        "duplicate_question_ratio": round(duplicate / total, 4) if total else 0.0,
        "valid_qa_ratio": round(valid_qa / total, 4) if total else 0.0,
        "covered_dimensions": dimensions,
        "total": total,
        "duplicate_count": duplicate,
        "no_evidence_count": sum(1 for c in cases if not c.get("evidence")),
    }


def import_uploaded_set(
    *,
    db: DatabaseService,
    name: str,
    template_type: str,
    dimension: str | None,
    cases: list[dict],
    source_file: str | None = None,
) -> dict:
    """格式校验 → 质量评估 → 入库（review_status=quality_checked，提示性门禁由前端确认后发布）。"""
    if template_type not in ("single", "multi"):
        raise ValueError(f"不支持的模板类型: {template_type}（single/multi）")
    errors = validate_cases(cases, template_type)
    if errors:
        raise ValueError("；".join(errors))
    set_id = db.save_uploaded_set(
        name=name,
        template_type=template_type,
        source_file=source_file,
        dimension=dimension,
    )
    db.save_uploaded_cases(set_id=set_id, cases=cases)
    quality = assess_quality(cases)
    db.update_uploaded_set(
        set_id,
        quality_snapshot=quality,
        total_cases=len(cases),
        review_status="quality_checked",
    )
    return {"set_id": set_id, "quality": quality, "total_cases": len(cases)}
