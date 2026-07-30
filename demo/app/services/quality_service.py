from __future__ import annotations

from app.services.database import DatabaseService


class QualityService:
    def __init__(self) -> None:
        self.database = DatabaseService()

    def run_quality_check(self, corpus_id: int) -> list[dict[str, object]]:
        cases = self.database.list_eval_cases(corpus_id=corpus_id)
        results = []
        for case in cases:
            passed = True
            reasons = []
            if not case["question"].strip():
                passed = False
                reasons.append("问题为空")
            if not case["gold_answer"].strip():
                passed = False
                reasons.append("答案为空")
            if not case["evidence"]:
                passed = False
                reasons.append("缺少证据")
            if case["must_have_points"] and case["must_have_points"][0] not in case["gold_answer"]:
                passed = False
                reasons.append("答案未覆盖要点")
            status = "quality_verified" if passed else "needs_revision"
            self.database.save_quality_check_result(
                case_id=case["case_id"],
                passed=passed,
                reason="; ".join(reasons) if reasons else "通过",
            )
            self.database.update_eval_case_status(case["case_id"], status)
            results.append({"case_id": case["case_id"], "passed": passed, "reason": "; ".join(reasons)})
        return results
