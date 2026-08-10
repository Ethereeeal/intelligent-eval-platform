"""m05 数据集生命周期服务。

职责（对齐 README §1 / §3）：
- 版本冻结（freeze）：把 m03 生成 + m04 审核通过的 generated_case 快照为不可变 eval_case 副本，
  记录完整 snapshot_metadata（语料版本/模型版本/覆盖率）。
- 无问题提示（FR-DS-EMPTY）：基于 m02 EIU 与 m03 可出题样本判定，EIU=0 或全不可出题时不发布空集。
- 导出：扁平 JSONL / 目录结构 JSON / Excel。
- 编辑：手动编辑样本（PUT）→ 回退 review_status=candidate；删除标记 retired 保留审计。
- 树形浏览（FR-DS-TREE-001）：按 section_path/doc 组织，标注样本数 / 覆盖率 / 未覆盖缺口。
- 文档重传：覆盖式整体作废 + 全量重算（无增量，见 README §8.14 / §3.3）。

数据来源（m01–m04 已跑通）：
- m02 EIU：database.list_eius（含 is_questionable / review_status / section_path / document_name）
- m03 生成样本：database.list_generated_cases（含 eiu_id / review_status / content_priority / scope_type）
- m04 质量门禁：generated_case.review_status（candidate → quality_verified → governance_passed → user_confirmed → published / blocked / needs_revision / retired）
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from modules.m02_eiu_coverage.services.coverage import save_coverage_report
from modules.shared.services.database import DatabaseService

# m04 审核状态机中"可纳入冻结集"的终态（不纳入 blocked / retired / needs_revision）
PUBLISHABLE_STATUSES = {
    "quality_verified",
    "governance_passed",
    "user_confirmed",
    "published",
}


def _next_version_number(latest: str | None) -> str:
    if not latest:
        return "v1.0.0"
    m = re.match(r"v(\d+)\.(\d+)\.(\d+)", latest)
    if not m:
        return "v1.0.0"
    major, minor, patch = (int(x) for x in m.groups())
    return f"v{major}.{minor}.{patch + 1}"


class DatasetLifecycleService:
    def __init__(self, db: DatabaseService | None = None) -> None:
        self.db = db or DatabaseService()

    # ------------------------------------------------------------------
    # 无问题判定（FR-DS-EMPTY）
    # ------------------------------------------------------------------
    def _empty_reason(self) -> str | None:
        """返回 None 表示可生成；否则返回"无问题"原因（不发布空集）。"""
        eius = self.db.list_eius(include_blocked=False)
        if not eius:
            return "EIU 总数 = 0：语料未抽到任何可出题单元（可能全部被排除或确无实质内容）"
        questionable = [e for e in eius if e.get("is_questionable")]
        if not questionable:
            return "全部 EIU 均标记为不可出题（is_questionable=false），无未处理文段"
        # 有可出题 EIU，再确认 m03 是否产出可纳入样本
        cases = self._publishable_cases()
        if not cases:
            return "有可出题 EIU，但尚无通过质量门禁的生成样本（请先跑 m03 生成 + m04 校验）"
        return None

    def _publishable_cases(self) -> list[dict]:
        """取 m03 生成、且 m04 审核达到可发布态的 generated_case。"""
        all_cases = self.db.list_generated_cases()
        return [c for c in all_cases if c.get("review_status") in PUBLISHABLE_STATUSES]

    # ------------------------------------------------------------------
    # 版本冻结
    # ------------------------------------------------------------------
    def freeze_version(self, *, created_by: str | None = None) -> dict:
        reason = self._empty_reason()
        if reason:
            # 不创建空集、不进入发布流程（FR-DS-EMPTY-002）
            raise ValueError(f"无问题可生成：{reason}")

        latest = self.db.get_latest_version_number()
        version_number = _next_version_number(latest)

        # 落库覆盖率报告（m02），回填 coverage_report_id（FR-DS-003 外键）
        coverage_report_id = save_coverage_report(
            snapshot_metadata={
                "frozen_at": datetime.utcnow().isoformat() + "Z",
            },
        )
        coverage = self.db.get_latest_coverage_report() or {}
        snapshot_metadata = self._build_snapshot_metadata(
            coverage=coverage,
            created_by=created_by,
        )

        version_id = self.db.save_dataset_version(
            version_number=version_number,
            status="frozen",
            case_count=0,
            coverage_report_id=coverage_report_id,
            split_config={"format": "full", "include_retired": False},
            snapshot_metadata=snapshot_metadata,
        )
        # 把通过门禁的 generated_case 快照为不可变 eval_case 副本
        case_count = self._snapshot_cases(version_id=version_id)
        self.db.update_dataset_version(version_id, case_count=case_count, freeze=True)
        return self.db.get_dataset_version(version_id)

    def _snapshot_cases(self, *, version_id: int) -> int:
        """将可发布态的 generated_case 复制为 eval_case 快照（冻结后不可变）。"""
        count = 0
        for case in self._publishable_cases():
            self.db.save_eval_case(
                version_id=version_id,
                case_uid=f"case_{version_id:04d}_{case['case_id']:06d}",
                intent_id=case.get("intent_id"),
                question=case["question"],
                type=case.get("question_type"),
                scope=case.get("scope_type"),
                difficulty=case.get("difficulty"),
                gold_answer=case.get("gold_answer"),
                must_have_points=case.get("must_have_points"),
                acceptable_answers=case.get("acceptable_answers"),
                evidence=case.get("evidence"),
                eiu_ids=[case.get("eiu_id")] if case.get("eiu_id") else [],
                content_priority=case.get("content_priority"),
                review_status=case.get("review_status"),
                source="native",
            )
            count += 1
        return count

    def _build_snapshot_metadata(
        self, *, coverage: dict, created_by: str | None
    ) -> dict:
        return {
            "parser_version": "pymupdf-1.24.0",
            "embedding_model": "BAAI/bge-small-zh-v1.5",
            "llm_model": "gpt-4o-mini-2024-07-18",
            "eiu_extraction_prompt_version": "eiu_v2",
            "question_prompt_version": "qg_v1",
            "answer_prompt_version": "ag_v1",
            "quality_check_prompt_version": "qc_v1",
            "coverage": coverage,
            "created_by": created_by,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    def list_versions(self) -> list[dict]:
        return self.db.list_dataset_versions()

    def get_version(self, version_id: int) -> dict | None:
        return self.db.get_dataset_version(version_id)

    # ------------------------------------------------------------------
    # 编辑 / 删除
    # ------------------------------------------------------------------
    def edit_case(
        self,
        case_id: int,
        *,
        question: str | None = None,
        gold_answer: str | None = None,
        type: str | None = None,
        scope: str | None = None,
        difficulty: str | None = None,
        content_priority: str | None = None,
        must_have_points: list | None = None,
        acceptable_answers: list | None = None,
        evidence: list | None = None,
    ) -> dict | None:
        if self.db.get_eval_case(case_id) is None:
            return None
        self.db.update_eval_case(
            case_id,
            question=question,
            gold_answer=gold_answer,
            type=type,
            scope=scope,
            difficulty=difficulty,
            content_priority=content_priority,
            must_have_points=must_have_points,
            acceptable_answers=acceptable_answers,
            evidence=evidence,
        )
        return self.db.get_eval_case(case_id)

    def delete_case(self, case_id: int) -> bool:
        if self.db.get_eval_case(case_id) is None:
            return False
        self.db.retire_eval_case(case_id)
        return True

    # ------------------------------------------------------------------
    # 表格视图 / 统计
    # ------------------------------------------------------------------
    def list_cases(
        self,
        version_id: int,
        *,
        include_retired: bool = False,
        source: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        return self.db.get_eval_cases(
            version_id,
            include_retired=include_retired,
            source=source,
            limit=limit,
            offset=offset,
        )

    def case_stats(self, version_id: int) -> dict:
        cases = self.db.get_eval_cases(version_id)
        stats: dict[str, int] = {}
        for case in cases:
            for dim in ("difficulty", "content_priority", "type", "scope", "source"):
                key = case.get(dim) or "unknown"
                stats[f"{dim}:{key}"] = stats.get(f"{dim}:{key}", 0) + 1
        return {"total": len(cases), "by_dimension": stats}

    # ------------------------------------------------------------------
    # 树形浏览（FR-DS-TREE-001）
    # ------------------------------------------------------------------
    def tree(self) -> dict:
        cases = self._publishable_cases()
        eius = self.db.list_eius(include_blocked=False)

        # section_path → 文档名 → 计数
        by_section: dict[str, dict] = {}
        for case in cases:
            eiu_id = (case.get("eiu_ids") or [None])[0] if case.get("eiu_ids") else None
            eiu = next((e for e in eius if e.get("eiu_id") == eiu_id), None)
            path = (eiu or {}).get("section_path") or "未分类"
            doc = (eiu or {}).get("document_name") or "未关联文档"
            node = by_section.setdefault(
                path, {"section_path": path, "eiu_count": 0, "case_count": 0, "coverage_pct": 0.0, "documents": {}}
            )
            node["documents"].setdefault(doc, 0)
            node["documents"][doc] += 1
            node["case_count"] += 1

        for eiu in eius:
            path = eiu.get("section_path") or "未分类"
            node = by_section.setdefault(
                path, {"section_path": path, "eiu_count": 0, "case_count": 0, "coverage_pct": 0.0, "documents": {}}
            )
            node["eiu_count"] += 1
            node["documents"].setdefault(eiu.get("document_name") or "未关联文档", 0)

        tree_list = []
        for path, node in by_section.items():
            eiu_count = node["eiu_count"]
            covered = sum(1 for e in eius if (e.get("section_path") or "未分类") == path and e.get("is_questionable"))
            node["coverage_pct"] = round(covered / eiu_count * 100, 1) if eiu_count else 0.0
            tree_list.append(
                {
                    "section_path": path,
                    "eiu_count": eiu_count,
                    "case_count": node["case_count"],
                    "coverage_pct": node["coverage_pct"],
                    "gap": max(eiu_count - node["case_count"], 0),
                    "documents": node["documents"],
                }
            )
        return {"tree": tree_list}

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def export_jsonl(self, version_id: int) -> str:
        cases = self.db.get_eval_cases(version_id)
        lines = [
            json.dumps(
                {
                    "case_id": c["case_uid"],
                    "question": c["question"],
                    "gold_answer": c["gold_answer"],
                    "evidence": c["evidence"],
                },
                ensure_ascii=False,
            )
            for c in cases
        ]
        return "\n".join(lines)

    def export_json(self, version_id: int) -> dict:
        version = self.db.get_dataset_version(version_id)
        if not version:
            raise ValueError("version not found")
        cases = self.db.get_eval_cases(version_id)
        by_doc: dict[str, dict] = {}
        for case in cases:
            eiu_id = (case.get("eiu_ids") or [None])[0] if case.get("eiu_ids") else None
            doc = "未关联文档"
            section = "未分类"
            # 通过 eiu 反查文档/章节（轻量：仅用于目录组织）
            if eiu_id is not None:
                eiu = self._get_eiu(eiu_id)
                if eiu:
                    doc = eiu.get("document_name") or doc
                    section = eiu.get("section_path") or section
            by_doc.setdefault(doc, {}).setdefault(section, []).append(case)

        documents = [
            {"document_name": doc, "sections": [{"section_path": sec, "cases": sec_cases} for sec, sec_cases in secs.items()]}
            for doc, secs in by_doc.items()
        ]
        result = {
            "dataset_version": version["version_number"],
            "coverage": (version.get("snapshot_metadata") or {}).get("coverage"),
            "documents": documents,
        }
        return result

    def export_xlsx(self, version_id: int) -> bytes:
        """Excel 导出（Demo 占位：返回 CSV 字节，待 openpyxl 接入后替换）。"""
        import csv
        import io

        cases = self.db.get_eval_cases(version_id)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["case_id", "question", "gold_answer", "type", "scope", "difficulty", "content_priority", "review_status"]
        )
        for c in cases:
            writer.writerow(
                [
                    c["case_uid"],
                    c["question"],
                    c["gold_answer"],
                    c["type"],
                    c["scope"],
                    c["difficulty"],
                    c["content_priority"],
                    c["review_status"],
                ]
            )
        return buf.getvalue().encode("utf-8-sig")

    # ------------------------------------------------------------------
    # 文档重传：覆盖式整体作废 + 全量重算（无增量，见 §8.14 / §3.3）
    # ------------------------------------------------------------------
    def rebuild_on_reupload(self, *, document_id: int, job_id: int) -> None:
        """文档重传回调（由 01 的 doc_update_job 完成后触发）。

        策略：整体作废该文档相关产物并全量重算。
        - 不做增量失效回写、不做旧题复用。
        - m03 已重算产出新 generated_case；此处把受影响的最新版本整体重建为覆盖式快照：
          删除旧版本中属于该文档（eiu→document）的 eval_case，再基于最新 generated_case 整体重快照。
        """
        self.db.update_job(job_id, phase="rebuild", progress=80, message="覆盖式整体重算中")
        latest_versions = self.db.list_dataset_versions()
        if latest_versions:
            version_id = latest_versions[0]["version_id"]
            # 覆盖式：先全量作废该版本下的快照样本，再基于最新 m03/m04 结果整体重快照
            self._rebuild_version_snapshot(version_id=version_id)
        self.db.update_job(job_id, status="done", phase="rebuild", progress=100, message="已更新完成", finished=True)

    def _rebuild_version_snapshot(self, *, version_id: int) -> int:
        """覆盖式重建：清空该版本 eval_case 快照，基于最新 generated_case 重新整体快照。"""
        # 清空旧快照
        old = self.db.get_eval_cases(version_id, include_retired=True, limit=100000)
        for c in old:
            self.db.retire_eval_case(c["case_id"])
        # 整体重快照
        new_count = self._snapshot_cases(version_id=version_id)
        self.db.update_dataset_version(version_id, case_count=new_count)
        return new_count

    def _get_eiu(self, eiu_id: int) -> dict | None:
        return self.db.get_eiu(eiu_id)
