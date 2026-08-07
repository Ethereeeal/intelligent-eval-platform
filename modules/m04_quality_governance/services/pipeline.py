"""m04 质量门禁：编排层（PipelineService）。

聚合 quality_checker（单题 5 项检查）、database（持久化 + 状态机）、
m03 generator（hard 失败自动重生成），对外提供与 README §4 API 一一对应的业务方法。

状态机（Demo 简化版）：
  candidate → quality_verified（全部通过）
            → needs_review（待人工确认，统一状态）
                ├── review_tag=answer_coverage   仅 soft 失败：证据覆盖/唯一性，
                │                                  不自动重生成，留人工复核
                └── review_tag=generation_issue  hard 失败（幻觉/偏题）自动回 m03
                                                 重生成多次仍失败，留人工处理

失败分流：
  hard 失败（faithfulness / question_relevance）→ 题目本身质量有问题
      → 自动调 m03 换角度重生成 → 新 case 自动重审 → 通过则 quality_verified
  soft 失败（evidence_sufficiency / uniqueness）→ 判断依赖文档全貌，LLM 与生成
      时看到的信息量一致，重生成无效 → 直接待人工确认（answer_coverage）

Demo 范围：5 项基础检查；治理审核 Skill / S0 强制规则 / 完整状态机延后（README §3）。
"""
from __future__ import annotations

import logging
from typing import Any

from modules.m03_generation.services.generator import CaseGenerator
from modules.m03_generation.services.prompts import DEFAULT_ANGLES
from modules.m04_quality_governance.models import QualityReport
from modules.m04_quality_governance.schemas import HARD_CHECKS
from modules.m04_quality_governance.services.prompts import CHECK_TYPES
from modules.m04_quality_governance.services.quality_checker import QualityChecker
from modules.shared.services.database import DatabaseService

STATUS_PASSED = "quality_verified"
STATUS_NEEDS_REVIEW = "needs_review"  # 统一"待人工确认"状态（软/硬两类失败共用）
TAG_ANSWER_COVERAGE = "answer_coverage"
TAG_GENERATION_ISSUE = "generation_issue"

# hard 失败自动重生成的上限（最多尝试 MAX_REGENERATE 个新角度）
MAX_REGENERATE = 2

logger = logging.getLogger(__name__)


class PipelineService:
    def __init__(self) -> None:
        self.database = DatabaseService()
        self.checker = QualityChecker()
        self.generator = CaseGenerator()

    # ------------------------------------------------------------------
    # 全量校验（POST /api/corpus/{corpus_id}/quality-check）
    # ------------------------------------------------------------------
    def run_quality_check(self, corpus_id: int) -> dict[str, Any]:
        """对语料库全部样本执行一轮质量校验，返回汇总（README §2.3）。"""
        cases = self.database.list_generated_cases(corpus_id)
        summary = self._empty_summary(corpus_id)
        summary["total_cases"] = len(cases)

        for case in cases:
            try:
                report = self._check_and_handle(case)
            except Exception as exc:  # 单题异常不阻断批量流程
                summary.setdefault("errors", []).append(
                    {"case_id": case["case_id"], "error": str(exc)}
                )
                continue

            if report.passed:
                summary["passed"] += 1
            else:
                summary["failed"] += 1
                summary["failed_cases"].append(
                    {
                        "case_id": case["case_id"],
                        "failed_checks": report.failed_checks,
                        "reason": self._failed_reason(report),
                        "review_tag": report.review_tag,
                    }
                )
            self._accumulate_by_check_type(summary, report)
        return summary

    # ------------------------------------------------------------------
    # 单题重跑（POST /api/cases/{case_id}/retry-check）
    # ------------------------------------------------------------------
    def retry_check(self, case_id: int) -> dict[str, Any]:
        case = self.database.get_generated_case(case_id)
        if case is None or case.get("review_status") == "retired":
            raise ValueError("case not found")
        report = self._check_and_handle(case)
        # 若原 case 已被替换（hard 失败重生成成功 → 原 case retired），
        # 返回替换关系，避免调用方误以为原 case 已通过
        current = self.database.get_generated_case(case_id)
        replaced = current and current["review_status"] == "retired"
        return {
            "case_id": case_id,
            "replaced_case_id": report.case_id if replaced else None,
            "passed": report.passed,
            "review_status": (
                "retired" if replaced else (
                    report.passed and STATUS_PASSED or STATUS_NEEDS_REVIEW
                )
            ),
            "review_tag": report.review_tag,
            "checks": [
                {
                    "check_id": None,
                    "case_id": report.case_id,
                    "check_type": item.check_type,
                    "passed": item.passed,
                    "reason": item.reason,
                }
                for item in report.checks
            ],
        }

    # ------------------------------------------------------------------
    # 查询（只读）
    # ------------------------------------------------------------------
    def get_case_checks(self, case_id: int) -> dict[str, Any] | None:
        """单题校验详情（GET /api/cases/{case_id}/quality-check）。"""
        case = self.database.get_generated_case(case_id)
        if case is None:
            return None
        checks = self.database.list_quality_checks(case_id)
        return {
            "case_id": case_id,
            "question": case["question"],
            "gold_answer": case["gold_answer"],
            "review_status": case["review_status"],
            "review_tag": case.get("review_tag"),
            "passed": bool(checks) and all(c["passed"] for c in checks),
            "checks": checks,
        }

    def get_results_summary(self, corpus_id: int) -> dict[str, Any]:
        """按已落库结果生成汇总（GET /api/corpus/{corpus_id}/quality-check/results）。"""
        cases = self.database.list_generated_cases(corpus_id)
        checks = self.database.list_quality_checks_by_corpus(corpus_id)

        summary = self._empty_summary(corpus_id)
        summary["total_cases"] = len(cases)

        # 按 case 分组
        by_case: dict[int, list[dict]] = {}
        for check in checks:
            by_case.setdefault(check["case_id"], []).append(check)

        for case_id, items in by_case.items():
            failed_checks = [c["check_type"] for c in items if not c["passed"]]
            if failed_checks:
                summary["failed"] += 1
                case = self.database.get_generated_case(case_id)
                summary["failed_cases"].append(
                    {
                        "case_id": case_id,
                        "failed_checks": failed_checks,
                        "reason": "; ".join(
                            c["reason"] for c in items if not c["passed"]
                        ),
                        "review_tag": (case or {}).get("review_tag"),
                    }
                )
            else:
                summary["passed"] += 1
            for check in items:
                key = check["check_type"]
                if key not in summary["by_check_type"]:
                    summary["by_check_type"][key] = {"passed": 0, "failed": 0}
                bucket = "passed" if check["passed"] else "failed"
                summary["by_check_type"][key][bucket] += 1
        return summary

    # ------------------------------------------------------------------
    # 核心：检查 + 失败分流 + 自动重生成
    # ------------------------------------------------------------------
    def _check_and_handle(self, case: dict[str, Any]) -> QualityReport:
        """单题完整处理：检查 → 分流 → 落库 → 更新状态机。

        - 全部通过 → quality_verified
        - 仅 soft 失败（证据覆盖/唯一性）→ needs_review + answer_coverage
        - hard 失败（幻觉/偏题）→ 自动回 m03 重生成，成功则新 case 通过；
          多次仍失败 → needs_review + generation_issue
        """
        report = self._check_and_persist(case)
        if report.passed:
            self.database.update_generated_case(
                case["case_id"], review_status=STATUS_PASSED, review_tag=None
            )
            return report

        hard_failed = [c for c in report.checks if c.check_type in HARD_CHECKS and not c.passed]

        # 仅 soft 失败：不自动重生成（判断信息量与生成时一致，重生成无效）
        if not hard_failed:
            report.review_tag = TAG_ANSWER_COVERAGE
            self._mark_needs_review(case["case_id"], TAG_ANSWER_COVERAGE)
            return report

        # hard 失败：自动回 m03 换角度重生成 + 新 case 自动重审
        new_report = self._regenerate_until_pass(case)
        if new_report is not None:
            return new_report

        # 多次重生成仍失败：待人工确认，标注题目生成有问题
        report.review_tag = TAG_GENERATION_ISSUE
        self._mark_needs_review(case["case_id"], TAG_GENERATION_ISSUE)
        return report

    def _regenerate_until_pass(self, case: dict[str, Any]) -> QualityReport | None:
        """hard 失败自动重生成：换角度最多 MAX_REGENERATE 次，返回通过的新 report。"""
        eiu_id = case.get("eiu_id")
        if eiu_id is None:
            # 用户上传路径无 EIU，无法自动重生成 → 留给人工
            self._mark_needs_review(case["case_id"], TAG_GENERATION_ISSUE)
            return None

        eiu = self.database.get_eiu(eiu_id)
        if eiu is None:
            self._mark_needs_review(case["case_id"], TAG_GENERATION_ISSUE)
            return None

        # 换角度：跳过当前 case 已用角度，依次尝试后续角度
        # intent_id 形如 "intent_{eiu_id}_{angle}"，split(_, 2) 取最后一个字段
        # （不能用 split("_")[-1]：value_lookup 会被误解析为 lookup）
        current_angle = str(case.get("intent_id", "")).split("_", 2)[-1]
        angles = [a for a in DEFAULT_ANGLES if a != current_angle]
        attempts = 0
        for angle in angles:
            if attempts >= MAX_REGENERATE:
                break
            attempts += 1
            try:
                generated = self.generator.generate_for_eiu(eiu, angle=angle)
                new_case = self.generator.save_case(generated)
            except Exception as exc:  # 单次重生成失败不阻断，尝试下一角度
                logger.warning(
                    "case %s 重生成(angle=%s)失败: %s", case["case_id"], angle, exc
                )
                continue

            # 新 case 自动重审
            try:
                new_report = self._check_and_persist(new_case)
            except Exception as exc:
                logger.warning(
                    "case %s 重生成后重审失败: %s", new_case["case_id"], exc
                )
                continue

            if new_report.passed:
                self.database.update_generated_case(
                    new_case["case_id"], review_status=STATUS_PASSED, review_tag=None
                )
                # 原失败 case 退役保留审计痕迹，新 case 正式替代
                self.database.retire_generated_case(case["case_id"])
                return new_report
            # 新 case 仍未通过：退役它，继续尝试下一角度
            self.database.retire_generated_case(new_case["case_id"])

        return None

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _check_and_persist(self, case: dict[str, Any]) -> QualityReport:
        """单题：清旧结果 → 5 项检查 → 逐项落库（不更新状态机）。"""
        self.database.clear_quality_checks(case["case_id"])
        report = self.checker.check_case(case)
        for item in report.checks:
            self.database.save_quality_check(
                case_id=case["case_id"],
                check_type=item.check_type,
                passed=item.passed,
                reason=item.reason,
            )
        return report

    def _mark_needs_review(self, case_id: int, tag: str) -> None:
        """置为统一待人工确认状态 + 失败标签。"""
        self.database.update_generated_case(
            case_id, review_status=STATUS_NEEDS_REVIEW, review_tag=tag
        )

    @staticmethod
    def _empty_summary(corpus_id: int) -> dict[str, Any]:
        return {
            "corpus_id": corpus_id,
            "total_cases": 0,
            "passed": 0,
            "failed": 0,
            "by_check_type": {
                check_type: {"passed": 0, "failed": 0} for check_type in CHECK_TYPES
            },
            "failed_cases": [],
            "errors": [],
        }

    @staticmethod
    def _accumulate_by_check_type(
        summary: dict[str, Any], report
    ) -> None:
        for item in report.checks:
            bucket = "passed" if item.passed else "failed"
            summary["by_check_type"][item.check_type][bucket] += 1

    @staticmethod
    def _failed_reason(report) -> str:
        reasons = [
            f"{item.check_type}: {item.reason}"
            for item in report.checks
            if not item.passed
        ]
        return "; ".join(reasons)
