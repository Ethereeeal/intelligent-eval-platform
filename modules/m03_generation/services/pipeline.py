"""m03 评测集生成：编排层（PipelineService）。

聚合 generator（规范题生成）、variation（泛化改写）、database（持久化），
对外提供与 README §6 API 一一对应的业务方法。

不涉及：跨段生成（FR-MH，Demo 延后）、反例/对抗题（FR-VAR-003，延后）、
难度统计（属覆盖清单/指标报告，见 m05）。
"""
from __future__ import annotations

import uuid
from typing import Any

from modules.m03_generation.services.generator import CaseGenerator
from modules.m03_generation.services.variation import VariationService
from modules.shared.services.database import DatabaseService


class PipelineService:
    def __init__(self) -> None:
        self.database = DatabaseService()
        self.generator = CaseGenerator()
        self.variation = VariationService()

    # ------------------------------------------------------------------
    # 批量生成（POST /api/corpus/{corpus_id}/cases/generate）
    # ------------------------------------------------------------------
    def generate_cases_for_corpus(
        self,
        corpus_id: int,
        *,
        angles: list[str] | None = None,
        include_variations: bool = False,
        variation_count: int = 2,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """为语料库下所有未覆盖 EIU 生成题目+答案（跳过已覆盖项）。

        angles: 出题角度列表；每个角度对同一 EIU 生成一道题（不重复计覆盖率）。
        dry_run: 仅返回待生成清单，不调用 LLM / 不落库。
        """
        eius = self.database.list_eius(corpus_id, questionable=True)
        covered = self.database.list_covered_eiu_ids(corpus_id)
        pending = [eiu for eiu in eius if eiu["eiu_id"] not in covered]

        if dry_run:
            return {
                "corpus_id": corpus_id,
                "total_questionable_eiu": len(eius),
                "already_covered": len(covered),
                "generated": 0,
                "failed": 0,
                "results": [],
                "pending_eius": [
                    {
                        "eiu_id": eiu["eiu_id"],
                        "eiu_type": eiu["eiu_type"],
                        "content_priority": eiu["content_priority"],
                        "statement": eiu["statement"],
                    }
                    for eiu in pending
                ],
            }

        results: list[dict[str, Any]] = []
        for eiu in pending:
            result = self._generate_for_eiu_with_angles(
                eiu,
                angles=angles,
                include_variations=include_variations,
                variation_count=variation_count,
            )
            results.append(result)

        return {
            "corpus_id": corpus_id,
            "total_questionable_eiu": len(eius),
            "already_covered": len(covered),
            "generated": sum(1 for r in results if r["error"] is None),
            "failed": sum(1 for r in results if r["error"] is not None),
            "results": results,
        }

    # ------------------------------------------------------------------
    # 单 EIU 生成（POST /api/eiu/{eiu_id}/generate-case）
    # ------------------------------------------------------------------
    def generate_case_for_eiu(
        self,
        eiu_id: int,
        *,
        angle: str = "primary",
        include_variations: bool = False,
        variation_count: int = 2,
    ) -> dict[str, Any]:
        eiu = self.database.get_eiu(eiu_id)
        if eiu is None:
            raise ValueError("EIU not found")
        result = self._generate_for_eiu_with_angles(
            eiu,
            angles=[angle],
            include_variations=include_variations,
            variation_count=variation_count,
        )
        return result

    # ------------------------------------------------------------------
    # 路径 2：用户上传问答对（POST /api/cases/generate-from-upload）
    # ------------------------------------------------------------------
    def generate_from_upload(
        self,
        *,
        corpus_id: int,
        document_id: int | None,
        question: str,
        answer: str,
        question_type: str,
        difficulty: str,
        content_priority: str,
        evidence: list[dict] | None = None,
        generate_variations: bool = False,
        variation_count: int = 2,
    ) -> dict[str, Any]:
        """保存用户上传的种子问答对，可选立即泛化。

        种子无 EIU（eiu_id=None）；intent_id 独立生成，
        后续泛化变体共享该 intent_id 与原答案。
        """
        seed = self.database.save_generated_case(
            intent_id=f"upload_{uuid.uuid4().hex[:12]}",
            eiu_id=None,
            corpus_id=corpus_id,
            document_id=document_id,
            question=question,
            question_type=question_type,
            difficulty=difficulty,
            scope_type="single_segment",
            gold_answer=answer,
            must_have_points=[],
            acceptable_answers=[],
            evidence=evidence or [],
            content_priority=content_priority,
            review_status="candidate",
        )

        variation_case_ids: list[int] = []
        if generate_variations:
            variants = self.variation.generate_variations(
                seed, count=variation_count
            )
            variation_case_ids = [v["case_id"] for v in variants]

        return {
            "seed_case": seed,
            "variation_case_ids": variation_case_ids,
            "generated_variations": len(variation_case_ids),
        }

    # ------------------------------------------------------------------
    # 泛化（POST 复用 /api/cases/{case_id}/variations 或批量生成内嵌）
    # ------------------------------------------------------------------
    def generate_variations_for_case(
        self,
        case_id: int,
        *,
        count: int = 3,
        styles: list[str] | None = None,
    ) -> dict[str, Any]:
        seed = self.database.get_generated_case(case_id)
        if seed is None or seed.get("review_status") == "retired":
            raise ValueError("case not found")
        variants = self.variation.generate_variations(
            seed, count=count, styles=styles
        )
        return {
            "seed_case_id": case_id,
            "intent_id": seed["intent_id"],
            "generated": len(variants),
            "variation_case_ids": [v["case_id"] for v in variants],
        }

    # ------------------------------------------------------------------
    # 查询 / 编辑 / 删除（委托 database）
    # ------------------------------------------------------------------
    def list_cases(
        self,
        corpus_id: int,
        *,
        priority: str | None = None,
        question_type: str | None = None,
        difficulty: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        return self.database.list_generated_cases(
            corpus_id,
            priority=priority,
            question_type=question_type,
            difficulty=difficulty,
            status=status,
        )

    def get_case(self, case_id: int) -> dict | None:
        return self.database.get_generated_case(case_id)

    def update_case(self, case_id: int, **fields: Any) -> dict | None:
        return self.database.update_generated_case(case_id, **fields)

    def delete_case(self, case_id: int) -> bool:
        """删除题目 = 人工放弃该 EIU（README DELETE 语义）。

        将 case 标记 retired；若这是该 EIU 下最后一个存活题，
        则同时把 EIU 标记为不可出题（is_questionable=0），
        避免下次批量生成又为该 EIU 出题（删了又生成、反复不过的循环）。
        """
        case = self.database.get_generated_case(case_id)
        if case is None or case.get("review_status") == "retired":
            return False
        deleted = self.database.retire_generated_case(case_id)
        if not deleted:
            return False

        eiu_id = case.get("eiu_id")
        if eiu_id is None:
            return True  # 用户上传题无 EIU，无需跳过
        # 该 EIU 下是否还有其他存活题（list_generated_cases 默认排除 retired）
        remaining_eiu_ids = {
            c.get("eiu_id")
            for c in self.database.list_generated_cases(case["corpus_id"])
            if c.get("eiu_id") is not None
        }
        if eiu_id not in remaining_eiu_ids:
            self.database.update_eiu(
                eiu_id,
                is_questionable=False,
                exclusion_reason="人工删除该 EIU 下全部题目：放弃出题",
            )
        return True

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _generate_for_eiu_with_angles(
        self,
        eiu: dict[str, Any],
        *,
        angles: list[str] | None,
        include_variations: bool,
        variation_count: int,
    ) -> dict[str, Any]:
        """对单个 EIU 按角度列表逐一生成，附带可选泛化。"""
        result: dict[str, Any] = {
            "eiu_id": eiu["eiu_id"],
            "eiu_type": eiu["eiu_type"],
            "statement": eiu["statement"],
            "case_ids": [],
            "variation_case_ids": [],
            "error": None,
        }
        angle_list = angles or ["primary"]
        for angle in angle_list:
            try:
                case = self.generator.generate_for_eiu(eiu, angle=angle)
                saved = self.generator.save_case(case)
                result["case_ids"].append(saved["case_id"])

                if include_variations:
                    variants = self.variation.generate_variations(
                        saved, count=variation_count
                    )
                    result["variation_case_ids"].extend(
                        v["case_id"] for v in variants
                    )
            except Exception as exc:  # 单个 EIU 失败不阻断批量流程
                result["error"] = str(exc)
                break
        return result
