"""m03 评测集生成：编排层（PipelineService）。

聚合 generator（规范题生成）、variation（泛化改写）、database（持久化），
对外提供与 README §6 API 一一对应的业务方法。

不涉及：跨段生成（FR-MH，Demo 延后）、反例/对抗题（FR-VAR-003，延后）、
难度统计（属覆盖清单/指标报告，见 m05）。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from modules.m03_generation.services.generator import CaseGenerator
from modules.m03_generation.services.variation import VariationService
from modules.shared.core.logging_config import get_logger
from modules.shared.services.database import DatabaseService

logger = get_logger(__name__)


class PipelineService:
    def __init__(self) -> None:
        self.database = DatabaseService()
        self.generator = CaseGenerator()
        self.variation = VariationService()
        # 生成进度（进程内，单进程 uvicorn 适用）：key = document_id（数字）或 "all"（全量）
        self._progress: dict[str | int, dict] = {}

    # ------------------------------------------------------------------
    # 生成进度（GET /api/cases/generate-progress，前端运行监测轮询）
    # ------------------------------------------------------------------
    def get_generate_progress(self, document_id: int | None = None) -> dict:
        """返回当前生成任务进度。document_id 为空时返回全量（corpus）任务进度。"""
        key: str | int = document_id if document_id is not None else "all"
        p = self._progress.get(key)
        if not p or p.get("status") != "running":
            return {
                "running": False,
                "document_id": document_id,
                "total": 0,
                "done": 0,
                "percent": 0,
            }
        total = p.get("total", 0)
        done = p.get("done", 0)
        percent = round(done / total * 100) if total else 0
        return {
            "running": True,
            "document_id": document_id,
            "total": total,
            "done": done,
            "percent": percent,
        }

    # ------------------------------------------------------------------
    # 批量生成（POST /api/cases/generate，按 document_id 或全量）
    # ------------------------------------------------------------------
    def generate_cases_for_corpus(
        self,
        *,
        angles: list[str] | None = None,
        include_variations: bool = False,
        variation_count: int = 2,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """为全部未覆盖 EIU 生成题目+答案（跳过已覆盖项，按文件维度组织）。

        angles: 出题角度列表；每个角度对同一 EIU 生成一道题（不重复计覆盖率）。
        dry_run: 仅返回待生成清单，不调用 LLM / 不落库。
        """
        eius = self.database.list_eius(questionable=True)
        covered = self.database.list_covered_eiu_ids()
        pending = [eiu for eiu in eius if eiu["eiu_id"] not in covered]

        if dry_run:
            return {
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
        total = len(pending)
        self._progress["all"] = {"document_id": None, "total": total, "done": 0, "status": "running"}
        try:
            for idx, eiu in enumerate(pending):
                try:
                    result = self._generate_for_eiu_with_angles(
                        eiu,
                        angles=angles,
                        include_variations=include_variations,
                        variation_count=variation_count,
                    )
                    results.append(result)
                finally:
                    self._progress["all"]["done"] = idx + 1
        finally:
            self._progress["all"]["status"] = "done"

        return {
            "total_questionable_eiu": len(eius),
            "already_covered": len(covered),
            "generated": sum(1 for r in results if r["error"] is None),
            "failed": sum(1 for r in results if r["error"] is not None),
            "results": results,
        }

    # ------------------------------------------------------------------
    # 单文档生成（上传链路调用：仅抽取当前文档 EIU、单文档隔离、不重抽其他文档）
    # ------------------------------------------------------------------
    def generate_cases_for_document(
        self,
        *,
        document_id: int,
        angles: list[str] | None = None,
        include_variations: bool = False,
        variation_count: int = 2,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """为单个文档重建问答对库（单文档隔离），可重复触发。

        隔离语义：
        - 仅读取该文档的 EIU（list_eius 按 document_id 过滤）；
        - 每次触发都是"重建"：先删该文档旧问答对，再按当前全部 EIU 重新生成，
          因此删掉旧问答对库后 EIU 仍在，可随时再次触发重新生成；
        - 不触碰其他文档的问答对与 EIU；
         - 跨文档不复用问答对，每个文档独立生成完整问答集。
        """
        eius = self.database.list_eius(
            questionable=True, document_id=document_id
        )

        if dry_run:
            covered = self.database.list_covered_eiu_ids(
                document_id=document_id
            )
            pending = [eiu for eiu in eius if eiu["eiu_id"] not in covered]
            return {
                "document_id": document_id,
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

        # 单文档隔离：重建语义——先清掉该文档旧问答对（EIU 保留在文档库，
        # 不受影响），随后按当前全部 EIU 重新生成；可重复触发生成多轮问答对库。
        self.database.delete_generated_cases_by_document(
            document_id=document_id
        )
        pending = list(eius)

        # 单文档生成进度（前端运行监测轮询展示百分比）
        total = len(pending)
        self._progress[document_id] = {
            "document_id": document_id,
            "total": total,
            "done": 0,
            "status": "running",
        }

        results: list[dict[str, Any]] = []
        try:
            for idx, eiu in enumerate(pending):
                try:
                    result = self._generate_for_eiu_with_angles(
                        eiu,
                        angles=angles,
                        include_variations=include_variations,
                        variation_count=variation_count,
                    )
                    results.append(result)
                finally:
                    self._progress[document_id]["done"] = idx + 1
        finally:
            self._progress[document_id]["status"] = "done"

        # 问答对库目录归属：继承源文档的 folder_path / purpose（与文档库目录同构）
        doc = self.database.get_document(document_id)
        doc_folder = (doc or {}).get("folder_path") or ""
        doc_purpose = (doc or {}).get("purpose") or "basic"
        all_case_ids: list[int] = []
        for r in results:
            all_case_ids.extend(r.get("case_ids", []))
            all_case_ids.extend(r.get("variation_case_ids", []))
        for cid in all_case_ids:
            self.database.update_generated_case(
                cid, folder_path=doc_folder, purpose=doc_purpose
            )

        return {
            "document_id": document_id,
            "total_questionable_eiu": len(eius),
            "already_covered": 0,  # 重建语义：触发前已删除该文档旧问答对，故 0
            "generated": sum(1 for r in results if r.get("error") is None and not r.get("reused")),
            "failed": sum(1 for r in results if r.get("error") is not None),
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
        document_id: int | None,
        question: str,
        answer: str,
        question_type: str,
        difficulty: str,
        content_priority: str,
        evidence: list[dict] | None = None,
        generate_variations: bool = False,
        variation_count: int = 2,
        folder_path: str | None = None,
        purpose: str | None = None,
    ) -> dict[str, Any]:
        """保存用户上传的种子问答对，可选立即泛化。

        种子无 EIU（eiu_id=None）；intent_id 独立生成，
        后续泛化变体共享该 intent_id 与原答案。
        folder_path / purpose：问答对库目录归属（缺省继承源文档）。
        """
        # 未显式指定目录时，继承源文档目录（与批量生成同构）
        if folder_path is None and document_id is not None:
            doc = self.database.get_document(document_id)
            folder_path = (doc or {}).get("folder_path") or ""
        if purpose is None:
            if document_id is not None:
                doc = self.database.get_document(document_id)
                purpose = (doc or {}).get("purpose") or "basic"
            else:
                purpose = "basic"
        seed = self.database.save_generated_case(
            intent_id=f"upload_{uuid.uuid4().hex[:12]}",
            eiu_id=None,
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
            folder_path=folder_path,
            purpose=purpose,
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
        *,
        document_id: int | None = None,
        priority: str | None = None,
        question_type: str | None = None,
        difficulty: str | None = None,
        status: str | None = None,
        folder_path: str | None = None,
        purpose: str | None = None,
    ) -> list[dict]:
        return self.database.list_generated_cases(
            document_id=document_id,
            priority=priority,
            question_type=question_type,
            difficulty=difficulty,
            status=status,
            folder_path=folder_path,
            purpose=purpose,
        )

    def get_case(self, case_id: int) -> dict | None:
        return self.database.get_generated_case(case_id)

    def update_case(self, case_id: int, **fields: Any) -> dict | None:
        return self.database.update_generated_case(case_id, **fields)

    def delete_case(self, case_id: int) -> bool:
        """删除题目（标记 retired），不影响 EIU 出题状态。

        删除问答对只移除该条样本，EIU 保持 is_questionable 原状，
        从而支持「删库后重新生成」：删掉某文档全部问答对后，
        EIU 仍在文档库，随时可再次触发生成（重建语义）。
        如需彻底放弃某 EIU 出题，请使用 EIU 层面的排除/标记接口。
        """
        case = self.database.get_generated_case(case_id)
        if case is None or case.get("review_status") == "retired":
            return False
        return self.database.retire_generated_case(case_id)

    # ------------------------------------------------------------------
    # 目录级导出（带目录结构，与输入文档库同构）
    # ------------------------------------------------------------------
    def export_cases_folder(
        self,
        folder_path: str | None = None,
        recursive: bool = True,
        purpose: str | None = None,
    ) -> dict[str, Any]:
        """导出问答对库目录树（含子目录），返回带层级结构的 JSON。

        结构：
          {
            "meta": {...},
            "tree": { <目录> : { "folders": {...}, "files": [case...] } },
            "flat_files": [ 所有命中的 case ]
          }
        目录树根按 purpose 分为「基础问题」「泛化问题」两个系统目录。
        """
        all_cases = self.database.list_generated_cases(purpose=purpose)
        # 仅保留指定目录范围（精确 + 递归子目录）
        if folder_path:
            fp = folder_path.rstrip("/")
            scoped = []
            for c in all_cases:
                cfp = (c.get("folder_path") or "").rstrip("/")
                if cfp == fp:
                    scoped.append(c)
                elif recursive and cfp.startswith(fp + "/"):
                    scoped.append(c)
            all_cases = scoped

        # 构建以 purpose 系统目录为根的树
        root: dict[str, Any] = {}
        flat_files: list[dict[str, Any]] = []

        def ensure_path(node: dict, parts: list[str]) -> dict:
            cur = node
            for p in parts:
                cur.setdefault("folders", {})
                cur.setdefault("files", [])
                cur = cur["folders"].setdefault(p, {})
            cur.setdefault("folders", {})
            cur.setdefault("files", [])
            return cur

        for c in all_cases:
            purpose_label = "泛化问题" if c.get("purpose") == "gen" else "基础问题"
            fp = (c.get("folder_path") or "").strip("/")
            parts = fp.split("/") if fp else []
            node = root.setdefault(purpose_label, {})
            target = ensure_path(node, parts)
            target["files"].append(c)
            flat_files.append(c)

        return {
            "meta": {
                "exported_at": datetime.now().isoformat(timespec="seconds"),
                "scope_folder": folder_path or "/",
                "recursive": recursive,
                "purpose": purpose,
                "total": len(flat_files),
            },
            "tree": root,
            "flat_files": flat_files,
        }

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
                # statement_norm 已在 generator.save_case 内随 GeneratedCase 落库
                result["case_ids"].append(saved["case_id"])

                if include_variations:
                    variants = self.variation.generate_variations(
                        saved, count=variation_count
                    )
                    result["variation_case_ids"].extend(
                        v["case_id"] for v in variants
                    )
            except Exception as exc:  # 单个 EIU 失败不阻断批量流程
                logger.warning(
                    "EIU 批量生成中断于 eiu_id=%s: %s", eiu.get("eiu_id"), exc
                )
                result["error"] = str(exc)
                break
        return result
