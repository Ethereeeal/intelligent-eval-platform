"""批量运行与单题复测编排（Demo 单进程后台线程）。"""
from __future__ import annotations

import threading
from datetime import datetime

from modules.m08_auto_evaluation.services.adapter import BaseAdapter
from modules.m08_auto_evaluation.services.diagnosis import diagnose
from modules.m08_auto_evaluation.services.intermediate_metrics import (
    normalize_intermediate_config,
    score_intermediate,
)
from modules.m08_auto_evaluation.services.metrics import score_case
from modules.m08_auto_evaluation.services.optimization import build_optimization
from modules.shared.services.database import DatabaseService


def _evaluate_case(
    sample: dict,
    adapter: BaseAdapter,
    intermediate_config: dict | None = None,
) -> dict:
    turns = sample.get("turns") or sample.get("input_turns")
    if turns:
        result = adapter.run_multi(
            turns, gold_answer=sample.get("gold_answer"), extra=sample
        )
    else:
        result = adapter.run_single(
            sample.get("question") or "",
            gold_answer=sample.get("gold_answer"),
            extra=sample,
        )
    scores = score_case(sample, result)
    normalized_intermediate = normalize_intermediate_config(intermediate_config)
    if normalized_intermediate["enabled"]:
        scores["intermediate"] = score_intermediate(
            sample,
            result or {},
            normalized_intermediate["nodes"],
        )
    diagnosis = diagnose(sample, result, scores)
    if scores.get("error"):
        status = "error"
    elif scores.get("score") is None:
        status = "unscored"
    elif scores.get("score") >= 0.5:
        status = "passed"
    else:
        status = "failed"
    return {
        "answer": (result or {}).get("answer"),
        "turn_outputs": (result or {}).get("turn_outputs"),
        "turn_trace": (result or {}).get("turn_trace"),
        "retrieved": (result or {}).get("retrieved"),
        "intermediate_reference": sample.get("intermediate_reference")
        or {
            "intent_label": sample.get("intent_label"),
            "rewrite_reference": sample.get("rewrite_reference"),
            "reference_contexts": sample.get("reference_contexts"),
        },
        "scores": scores,
        "diagnosis": diagnosis,
        "status": status,
        "error_message": (result or {}).get("error"),
    }


def _base_result_fields(sample: dict) -> dict:
    return {
        "case_uid": sample.get("case_uid") or "",
        "question": sample.get("question") or "",
        "gold_answer": sample.get("gold_answer"),
        "input_turns": sample.get("turns") or sample.get("input_turns"),
        "difficulty": sample.get("difficulty"),
        "dimension": sample.get("dimension"),
        "source": sample.get("source") or "doc_generated",
    }


def _save_error_book(db: DatabaseService, *, run_id: int, result_id: int, sample: dict, diagnosis: str | None) -> None:
    if diagnosis:
        db.save_error_book_item(
            run_id=run_id,
            result_id=result_id,
            case_uid=sample.get("case_uid"),
            diagnosis=diagnosis,
            optimization=build_optimization(diagnosis),
        )


def start_run_async(
    *,
    run_id: int,
    samples: list[dict],
    adapter: BaseAdapter,
    intermediate_config: dict | None = None,
) -> None:
    """逐题运行；取消在当前请求结束后生效，整轮异常会收敛为 failed。"""

    def _run() -> None:
        db = DatabaseService()
        try:
            db.update_evaluation_run(
                run_id,
                status="running",
                total=len(samples),
                progress=0,
                started_at=datetime.utcnow(),
            )
            for idx, sample in enumerate(samples, start=1):
                current = db.get_evaluation_run(run_id)
                if current is None:
                    return
                if current.get("status") in {"cancelling", "cancelled"}:
                    db.update_evaluation_run(
                        run_id, status="cancelled", finished_at=datetime.utcnow()
                    )
                    return
                try:
                    evaluated = _evaluate_case(sample, adapter, intermediate_config)
                except Exception as exc:  # noqa: BLE001 — 单题异常不中断整轮
                    evaluated = {
                        "status": "error",
                        "diagnosis": "D9",
                        "error_message": str(exc)[:500],
                    }
                result_id = db.save_evaluation_case_result(
                    run_id=run_id, **_base_result_fields(sample), **evaluated
                )
                _save_error_book(
                    db,
                    run_id=run_id,
                    result_id=result_id,
                    sample=sample,
                    diagnosis=evaluated.get("diagnosis"),
                )
                db.update_evaluation_run(
                    run_id,
                    finished=idx,
                    progress=int(idx / len(samples) * 100) if samples else 100,
                )
            db.update_evaluation_run(
                run_id,
                status="done",
                progress=100,
                finished_at=datetime.utcnow(),
            )
        except Exception:  # noqa: BLE001 — 后台线程必须形成可见终态
            try:
                if db.get_evaluation_run(run_id) is not None:
                    db.update_evaluation_run(
                        run_id, status="failed", finished_at=datetime.utcnow()
                    )
            except Exception:  # noqa: BLE001 — 数据库不可用时线程只能安全退出
                pass

    threading.Thread(target=_run, daemon=True).start()


def start_case_retry_async(
    *,
    run_id: int,
    source_result: dict,
    adapter: BaseAdapter,
    analysis_threshold: float = 0.5,
    intermediate_config: dict | None = None,
) -> int:
    """创建一条不可覆盖原结果的单题复测记录，并在后台执行。"""
    db = DatabaseService()
    attempts = db.list_evaluation_result_attempts(source_result["result_id"])
    attempt_no = max((int(item.get("attempt_no") or 1) for item in attempts), default=1) + 1
    attempt_id = db.save_evaluation_case_result(
        run_id=run_id,
        **_base_result_fields(source_result),
        parent_result_id=source_result["result_id"],
        attempt_no=attempt_no,
        status="pending",
    )

    def _retry() -> None:
        retry_db = DatabaseService()
        try:
            evaluated = _evaluate_case(source_result, adapter, intermediate_config)
        except Exception as exc:  # noqa: BLE001
            evaluated = {
                "status": "error",
                "diagnosis": "D9",
                "error_message": str(exc)[:500],
            }
        retry_db.update_evaluation_case_result(attempt_id, **evaluated)
        original_issue = retry_db.get_error_book_item_for_result(
            source_result["result_id"],
            run_id=run_id,
            case_uid=source_result.get("case_uid"),
        )
        regression_entry = {
            "attempt_result_id": attempt_id,
            "status": evaluated["status"],
            "score": (evaluated.get("scores") or {}).get("score"),
            "analysis_threshold": analysis_threshold,
            "created_at": datetime.utcnow().isoformat(),
        }
        if original_issue:
            history = list(original_issue.get("regression") or [])
            history.append(regression_entry)
            updates = {"regression": history}
            retry_score = (evaluated.get("scores") or {}).get("score")
            if (
                original_issue.get("status") == "processed"
                and retry_score is not None
                and float(retry_score) >= analysis_threshold
                and evaluated["status"] != "error"
            ):
                updates["status"] = "verified"
            retry_db.update_error_book_item(original_issue["item_id"], **updates)

    threading.Thread(target=_retry, daemon=True).start()
    return attempt_id
