"""批量运行编排（BRD §9.1 FR-RUN-001）：异步线程，进度写入 evaluation_run。"""
from __future__ import annotations

import threading
from datetime import datetime

from modules.m08_auto_evaluation.services.adapter import BaseAdapter
from modules.m08_auto_evaluation.services.diagnosis import diagnose
from modules.m08_auto_evaluation.services.metrics import score_case
from modules.m08_auto_evaluation.services.optimization import build_optimization
from modules.shared.services.database import DatabaseService


def start_run_async(*, run_id: int, samples: list[dict], adapter: BaseAdapter) -> None:
    """后台线程执行批量运行（Demo 单进程适用）。"""

    def _run() -> None:
        db = DatabaseService()
        db.update_evaluation_run(
            run_id,
            status="running",
            total=len(samples),
            progress=0,
            started_at=datetime.utcnow(),
        )
        for idx, sample in enumerate(samples, start=1):
            try:
                if sample.get("turns"):
                    result = adapter.run_multi(
                        sample["turns"],
                        gold_answer=sample.get("gold_answer"),
                        extra=sample,
                    )
                else:
                    result = adapter.run_single(
                        sample.get("question") or "",
                        gold_answer=sample.get("gold_answer"),
                        extra=sample,
                    )
                scores = score_case(sample, result)
                diagnosis = diagnose(sample, result, scores)
                if scores.get("error"):
                    status = "error"
                elif scores.get("score") is None:
                    # 无金标准（如仅拒答/样本缺陷）：不误判为 failed
                    status = "unscored"
                elif scores.get("score") >= 0.5:
                    status = "passed"
                else:
                    status = "failed"
                db.save_evaluation_case_result(
                    run_id=run_id,
                    case_uid=sample.get("case_uid") or "",
                    question=sample.get("question") or "",
                    gold_answer=sample.get("gold_answer"),
                    difficulty=sample.get("difficulty"),
                    dimension=sample.get("dimension"),
                    source=sample.get("source") or "doc_generated",
                    answer=(result or {}).get("answer"),
                    turn_outputs=(result or {}).get("turn_outputs"),
                    retrieved=(result or {}).get("retrieved"),
                    scores=scores,
                    diagnosis=diagnosis,
                    status=status,
                    error_message=(result or {}).get("error"),
                )
                if diagnosis:
                    db.save_error_book_item(
                        run_id=run_id,
                        case_uid=sample.get("case_uid"),
                        diagnosis=diagnosis,
                        optimization=build_optimization(diagnosis),
                    )
            except Exception as exc:  # noqa: BLE001 — 单题异常不中断整轮
                db.save_evaluation_case_result(
                    run_id=run_id,
                    case_uid=sample.get("case_uid") or "",
                    question=sample.get("question") or "",
                    gold_answer=sample.get("gold_answer"),
                    difficulty=sample.get("difficulty"),
                    dimension=sample.get("dimension"),
                    source=sample.get("source") or "doc_generated",
                    status="error",
                    error_message=str(exc)[:500],
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

    threading.Thread(target=_run, daemon=True).start()
