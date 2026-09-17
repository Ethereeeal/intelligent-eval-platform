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
    def _empty_reason(self, document_ids: list[int] | None = None) -> str | None:
        """返回 None 表示可生成；否则返回"无问题"原因（不发布空集）。"""
        eius = self.db.list_eius(include_blocked=False)
        if not eius:
            return "EIU 总数 = 0：语料未抽到任何可出题单元（可能全部被排除或确无实质内容）"
        questionable = [e for e in eius if e.get("is_questionable")]
        if not questionable:
            return "全部 EIU 均标记为不可出题（is_questionable=false），无未处理文段"
        # 有可出题 EIU，再确认 m03 是否产出可纳入样本
        cases = self._publishable_cases(document_ids=document_ids)
        if not cases:
            return "有可出题 EIU，但尚无通过质量门禁的生成样本（请先跑 m03 生成 + m04 校验）"
        return None

    def _publishable_cases(self, document_ids: list[int] | None = None) -> list[dict]:
        """取 m03 生成、且 m04 审核达到可发布态的 generated_case。

        document_ids 非空时仅返回所选文档的可发布 case（评测集按选择合并）。
        """
        all_cases = self.db.list_generated_cases()
        if document_ids:
            doc_set = set(document_ids)
            all_cases = [c for c in all_cases if c.get("document_id") in doc_set]
        return [c for c in all_cases if c.get("review_status") in PUBLISHABLE_STATUSES]

    def _assert_selected_uploads_quality(self, uploaded_set_ids: list[int] | None) -> None:
        """上传集门禁：证据可缺失，但问题/答案必须完整有效；重复题仅作提示统计。"""
        for set_id in uploaded_set_ids or []:
            item = self.db.get_uploaded_set(set_id)
            if item is None:
                raise ValueError(f"上传评测集 {set_id} 不存在")
            quality = item.get("quality_snapshot") or {}
            if quality.get("total", item.get("total_cases", 0)) <= 0:
                raise ValueError(f"上传评测集“{item.get('name', set_id)}”为空")
            if quality.get("data_completeness_rate", 0) < 1 or quality.get("valid_qa_ratio", 0) < 1:
                raise ValueError(f"上传评测集“{item.get('name', set_id)}”未通过质量门禁（需问题/答案完整且有效）")

    def _scenario_for_draft(
        self,
        *,
        scenario_id: int | None,
        name: str,
        description: str | None,
        tags: list[str] | None,
        created_by: str | None,
    ) -> dict:
        if scenario_id is not None:
            scenario = self.db.get_scenario(scenario_id)
            if scenario is None:
                raise ValueError(f"业务场景 {scenario_id} 不存在")
            return scenario
        # 同名场景复用，避免每次生成都产生一个无法检索的新场景。
        existing = next((item for item in self.db.list_scenarios() if item["name"] == name.strip()), None)
        return existing or self.db.create_scenario(
            name=name,
            description=description,
            tags=tags,
            created_by=created_by,
        )

    def create_draft(
        self,
        *,
        name: str,
        scenario_id: int | None = None,
        scenario_name: str | None = None,
        scenario_description: str | None = None,
        scenario_tags: list[str] | None = None,
        created_by: str | None = None,
        document_ids: list[int] | None = None,
        uploaded_set_ids: list[int] | None = None,
        public_selections: list[dict] | None = None,
        generation_config: dict | None = None,
        parent_version_id: int | None = None,
    ) -> dict:
        """将本次生成结果保存为可人工校验的 draft，不直接进入可执行评测。"""
        has_external = bool(uploaded_set_ids) or any(
            int(item.get("count", 0)) > 0 for item in (public_selections or []) if isinstance(item, dict)
        )
        scenario = self._scenario_for_draft(
            scenario_id=scenario_id,
            name=scenario_name or name,
            description=scenario_description,
            tags=scenario_tags,
            created_by=created_by,
        )
        self._assert_selected_uploads_quality(uploaded_set_ids)
        if not document_ids and not has_external:
            raise ValueError("草稿至少需要选择一个文档、上传评测集或公共库题目")
        latest = self.db.get_latest_version_number()
        version_number = _next_version_number(latest)
        snapshot_metadata = self._build_snapshot_metadata(
            coverage={"scope": "draft_selected_eval_set"}, created_by=created_by
        )
        snapshot_metadata.update({
            "composition_name": name,
            "lifecycle_stage": "draft",
            "scenario_name": scenario["name"],
            "generation_config": generation_config or {},
            "document_ids": document_ids or [],
            "uploaded_set_ids": uploaded_set_ids or [],
            "public_selections": public_selections or [],
            "generated_library": {"role": "intermediate_artifact", "origin": "document_library"},
        })
        version_id = self.db.save_dataset_version(
            scenario_id=scenario["scenario_id"],
            parent_version_id=parent_version_id,
            iteration_no=self._next_iteration_no(scenario["scenario_id"]),
            version_number=version_number,
            status="draft",
            case_count=0,
            split_config={"format": "full", "include_retired": False},
            snapshot_metadata=snapshot_metadata,
        )
        case_count = self._snapshot_cases(
            version_id=version_id,
            # [] 表示本次没有选文档；不能因为 document_ids 为空就把生成库全量带入外部题草稿。
            document_ids=document_ids or [],
            include_all=True,
        )
        case_count += self._materialize_external(
            version_id=version_id,
            uploaded_set_ids=uploaded_set_ids,
            public_selections=public_selections,
        )
        if case_count <= 0:
            raise ValueError("所选来源没有可保存的评测题，请先完成生成或导入")
        self.db.update_dataset_version(version_id, case_count=case_count)
        self.db.save_evaluation_iteration(
            scenario_id=scenario["scenario_id"],
            version_id=version_id,
            parent_version_id=parent_version_id,
            optimization_type="dataset",
            status="draft",
            summary="首次生成草稿，等待质量检查与人工校验",
            metadata_json={"stage": "generation"},
            created_by=created_by or "web",
        )
        return self.db.get_dataset_version(version_id) or {}

    def _next_iteration_no(self, scenario_id: int) -> int:
        versions = [item for item in self.db.list_dataset_versions() if item.get("scenario_id") == scenario_id]
        return max([int(item.get("iteration_no") or 0) for item in versions] + [0]) + 1

    def clone_version(self, version_id: int, *, created_by: str | None = None) -> dict:
        source = self.db.get_dataset_version(version_id)
        if source is None:
            raise ValueError("source version not found")
        if source.get("status") not in {"frozen", "published"}:
            raise ValueError("只有冻结或发布版本可以克隆草稿")
        scenario_id = source.get("scenario_id")
        if scenario_id is None:
            scenario = self._scenario_for_draft(
                scenario_id=None,
                name=(source.get("snapshot_metadata") or {}).get("composition_name") or "未命名业务场景",
                description="从历史评测集版本补建的业务场景",
                tags=[],
                created_by=created_by,
            )
            scenario_id = scenario["scenario_id"]
        name = f"{(source.get('snapshot_metadata') or {}).get('composition_name') or source.get('version_number') or '评测集'} · 草稿"
        metadata = dict(source.get("snapshot_metadata") or {})
        metadata.update({"composition_name": name, "lifecycle_stage": "draft", "cloned_from_version_id": version_id})
        new_id = self.db.save_dataset_version(
            scenario_id=scenario_id,
            parent_version_id=version_id,
            iteration_no=self._next_iteration_no(scenario_id),
            version_number=_next_version_number(self.db.get_latest_version_number()),
            status="draft",
            case_count=0,
            split_config=source.get("split_config") or {"format": "full", "include_retired": False},
            snapshot_metadata=metadata,
        )
        count = 0
        for case in self.db.get_eval_cases(version_id, include_retired=False, limit=100000):
            self.db.save_eval_case(
                version_id=new_id,
                case_uid=f"draft_{new_id:04d}_{case['case_id']:06d}",
                intent_id=case.get("intent_id"),
                question=case["question"],
                type=case.get("type"),
                scope=case.get("scope"),
                difficulty=case.get("difficulty"),
                gold_answer=case.get("gold_answer"),
                must_have_points=case.get("must_have_points"),
                acceptable_answers=case.get("acceptable_answers"),
                evidence=case.get("evidence"),
                eiu_ids=case.get("eiu_ids"),
                content_priority=case.get("content_priority"),
                review_status="candidate",
                auto_quality_status=case.get("auto_quality_status") or "pending",
                manual_review_status="pending",
                source=case.get("source") or "native",
            )
            count += 1
        self.db.update_dataset_version(new_id, case_count=count)
        self.db.save_evaluation_iteration(
            scenario_id=scenario_id,
            version_id=new_id,
            parent_version_id=version_id,
            optimization_type="dataset",
            status="draft",
            summary="从冻结版本克隆，等待评测集优化",
            metadata_json={"stage": "clone"},
            created_by=created_by or "web",
        )
        return self.db.get_dataset_version(new_id) or {}

    def freeze_draft(self, version_id: int, *, actor: str | None = None) -> dict:
        version = self.db.get_dataset_version(version_id)
        if version is None:
            raise ValueError("version not found")
        if version.get("status") != "draft":
            raise ValueError("只有草稿版本可以冻结")
        cases = self.db.get_eval_cases(version_id, include_retired=False, limit=100000)
        if not cases:
            raise ValueError("草稿没有可冻结的评测题")
        blocked = [case for case in cases if case.get("auto_quality_status") != "passed" or case.get("manual_review_status") != "approved"]
        if blocked:
            pending_quality = sum(case.get("auto_quality_status") != "passed" for case in blocked)
            pending_review = sum(case.get("manual_review_status") != "approved" for case in blocked)
            raise ValueError(f"草稿尚未满足冻结门禁：{pending_quality} 条自动质检未通过，{pending_review} 条未完成人工确认")
        metadata = dict(version.get("snapshot_metadata") or {})
        metadata.update({"lifecycle_stage": "frozen", "frozen_by": actor or "web", "frozen_at": datetime.utcnow().isoformat() + "Z"})
        self.db.update_dataset_version(version_id, status="frozen", snapshot_metadata=metadata, freeze=True)
        if version.get("scenario_id") is not None:
            self.db.save_evaluation_iteration(
                scenario_id=version["scenario_id"],
                version_id=version_id,
                parent_version_id=version.get("parent_version_id"),
                optimization_type="dataset",
                status="frozen",
                summary="人工校验完成，版本已冻结，可进入评测运行",
                metadata_json={"stage": "freeze"},
                created_by=actor or "web",
            )
        return self.db.get_dataset_version(version_id) or {}

    # ------------------------------------------------------------------
    # 版本冻结
    # ------------------------------------------------------------------
    def freeze_version(
        self,
        *,
        name: str | None = None,
        created_by: str | None = None,
        document_ids: list[int] | None = None,
        uploaded_set_ids: list[int] | None = None,
        public_selections: list[dict] | None = None,
        generation_config: dict | None = None,
    ) -> dict:
        """冻结生成库为不可变版本，并把用户指定的上传库 / 公共库题一并物化进同一版本。

        方案 B（物化进 version）：
        评测集在冻结阶段一次性定稿——生成库是由文档库文档经 m03 生成、m04 质检形成的
        中间产物（native），再与选中的上传库 / 公共库题快照进
        同一个 dataset_version 的 eval_case，用 source 字段区分（native / uploaded / public）。
        冻结后该版本是一个真正完整、不可变的评测集，两次评测取同一版本得到完全相同的
        题目，满足审计溯源与失败本诊断需求。

        public_selections 每项形如 {"set_id": int, "count": int}，按公共库维度（每个 set
        对应一个维度文件）抽取指定题数。
        """
        has_external = bool(uploaded_set_ids) or any(
            int(item.get("count", 0)) > 0 for item in (public_selections or []) if isinstance(item, dict)
        )
        reason = self._empty_reason(document_ids=document_ids) if document_ids else None
        if reason and not has_external:
            # 不创建空集、不进入发布流程（FR-DS-EMPTY-002）
            raise ValueError(f"无问题可生成：{reason}")

        latest = self.db.get_latest_version_number()
        version_number = _next_version_number(latest)

        # 门禁以本次评测集为单位：文档题只接纳 m04 可发布态，上传集须通过自身质量检查。
        # 全库覆盖率/Block 对账率仅作为平台健康指标，不阻断单次冻结。
        coverage_report_id = None
        coverage = {"scope": "selected_eval_set"}
        self._assert_selected_uploads_quality(uploaded_set_ids)
        snapshot_metadata = self._build_snapshot_metadata(
            coverage=coverage,
            created_by=created_by,
        )
        snapshot_metadata.update({
            "composition_name": name or f"评测集库 {version_number}",
            "generation_config": generation_config or {},
            "document_ids": document_ids or [],
            "generated_library": {
                "role": "intermediate_artifact",
                "origin": "document_library",
                "pipeline": ["m03_generation", "m04_quality_governance"],
            },
            "uploaded_set_ids": uploaded_set_ids or [],
            "public_selections": public_selections or [],
        })

        version_id = self.db.save_dataset_version(
            version_number=version_number,
            status="frozen",
            case_count=0,
            coverage_report_id=coverage_report_id,
            split_config={"format": "full", "include_retired": False},
            snapshot_metadata=snapshot_metadata,
        )
        # 把通过门禁的 generated_case 快照为不可变 eval_case 副本（按选择合并，保留重复题）
        case_count = self._snapshot_cases(version_id=version_id, document_ids=document_ids)
        # 方案 B：把选中的上传库 / 公共库题物化进同一版本
        case_count += self._materialize_external(
            version_id=version_id,
            uploaded_set_ids=uploaded_set_ids,
            public_selections=public_selections,
        )
        self.db.update_dataset_version(version_id, case_count=case_count, freeze=True)
        return self.db.get_dataset_version(version_id)

    def materialize_external(
        self,
        *,
        version_id: int,
        uploaded_set_ids: list[int] | None = None,
        public_selections: list[dict] | None = None,
    ) -> dict:
        """对已冻结的生成库版本追加物化外部题（上传库 / 公共库）。

        用于"生成时未选外部题，后续在评测集库页面追加纳入"的场景。物化题写入同一
        version 的 eval_case（source=uploaded / public），并返回更新后的版本。
        """
        version = self.db.get_dataset_version(version_id)
        if version is None:
            raise ValueError(f"version {version_id} 不存在")
        if version.get("status") != "frozen":
            raise ValueError("仅冻结版本可物化追加外部题")
        added = self._materialize_external(
            version_id=version_id,
            uploaded_set_ids=uploaded_set_ids,
            public_selections=public_selections,
        )
        new_count = self.db.count_eval_cases(version_id) + added
        self.db.update_dataset_version(version_id, case_count=new_count)
        return self.db.get_dataset_version(version_id)

    def _snapshot_cases(
        self,
        *,
        version_id: int,
        document_ids: list[int] | None = None,
        include_all: bool = False,
    ) -> int:
        """将可发布态的 generated_case 复制为 eval_case 快照（冻结后不可变）。

        不对问题做去重：同一问题来自不同文档、来源或生成批次时，仍作为独立评测样本
        快照保存，保证用户选择的题目数量和来源不被静默改变。
        document_ids 非空时仅快照所选文档的可发布 case。
        """
        cases = self.db.list_generated_cases()
        if document_ids is not None:
            doc_set = set(document_ids)
            cases = [case for case in cases if case.get("document_id") in doc_set]
        cases = [case for case in cases if case.get("review_status") != "retired"]
        if not include_all:
            cases = [case for case in cases if case.get("review_status") in PUBLISHABLE_STATUSES]
        count = 0
        for case in cases:
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
                auto_quality_status="passed" if case.get("review_status") in PUBLISHABLE_STATUSES else "pending",
                manual_review_status="pending",
                source="native",
            )
            count += 1
        return count

    def _materialize_external(
        self,
        *,
        version_id: int,
        uploaded_set_ids: list[int] | None = None,
        public_selections: list[dict] | None = None,
    ) -> int:
        """把上传库 / 公共库的选中题物化进指定 version 的 eval_case（方案 B 核心）。

        - 上传库：uploaded_set_ids 中每个 set 的全部题（默认全选）落为 source=uploaded。
        - 公共库：public_selections 每项可为 {"set_id": int, "count": int} 或
          {"dimension": str, "count": int}，从指定评测集或维度中随机抽取题目，
          落为 source=public。

        返回本次物化的题数。公共库真实数据未导入时（list 为空）按 0 题处理，不报错，
        保证机制可跑、后端数据接入后自动生效。
        """
        import random

        added = 0
        base_uid = f"ext_{version_id:04d}"

        for set_id in uploaded_set_ids or []:
            cases = self.db.list_uploaded_cases(set_id)
            set_name = (self.db.get_uploaded_set(set_id) or {}).get("name", f"uploaded#{set_id}")
            for idx, case in enumerate(cases):
                self.db.save_eval_case(
                    version_id=version_id,
                    case_uid=f"{base_uid}_up_{set_id}_{idx:06d}",
                    question=case["q"],
                    gold_answer=case.get("a"),
                    evidence=case.get("evidence"),
                    source="uploaded",
                    review_status="quality_checked",
                    auto_quality_status="passed",
                    manual_review_status="pending",
                )
                added += 1

        for sel in public_selections or []:
            set_id = sel.get("set_id")
            dimension = str(sel.get("dimension") or "").strip()
            count = int(sel.get("count", 0))
            if count <= 0 or (not set_id and not dimension):
                continue
            cases = self.db.list_public_cases(set_id) if set_id else self.db.list_public_cases_by_dimension(dimension)
            if not cases:
                continue
            sampled = cases if count >= len(cases) else random.sample(cases, count)
            public_key = set_id if set_id else dimension
            for idx, case in enumerate(sampled):
                self.db.save_eval_case(
                    version_id=version_id,
                    case_uid=f"{base_uid}_pub_{public_key}_{idx:06d}",
                    question=case["q"],
                    gold_answer=case.get("a"),
                    evidence=case.get("evidence"),
                    source="public",
                    review_status="quality_checked",
                    auto_quality_status="passed",
                    manual_review_status="pending",
                )
                added += 1

        return added

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
    # 冻结前人工修订 / 复检
    # ------------------------------------------------------------------
    def revise_candidate_case(
        self, case_id: int, *, actor: str | None = None, **fields
    ) -> dict | None:
        """修订 m03 候选题并强制回退到待质检状态。

        已冻结版本保存的是独立 eval_case 快照，不会被这里的源题修改影响。
        """
        case = self.db.get_generated_case(case_id)
        if case is None:
            return None
        if case.get("review_status") == "retired":
            raise ValueError("retired case cannot be revised")

        changed_fields = sorted(fields)
        if not changed_fields:
            raise ValueError("at least one editable field is required")
        self.db.save_audit(
            operation="dataset_case.revise",
            target_type="generated_case",
            target_id=str(case_id),
            actor=actor or "web",
            detail={"changed_fields": changed_fields, "review_status": "candidate"},
        )
        return self.db.update_generated_case(
            case_id,
            **fields,
            review_status="candidate",
            review_tag=None,
        )

    def _quality_pipeline(self):
        from modules.m04_quality_governance.services.pipeline import PipelineService

        return PipelineService()

    def recheck_candidate_case(self, case_id: int, *, actor: str | None = None) -> dict | None:
        """对修订后的候选题调用 m04 单题复检。"""
        case = self.db.get_generated_case(case_id)
        if case is None:
            return None
        if case.get("review_status") != "candidate":
            raise ValueError("only candidate cases can be rechecked")

        result = self._quality_pipeline().retry_check(case_id)
        self.db.save_audit(
            operation="dataset_case.recheck",
            target_type="generated_case",
            target_id=str(case_id),
            actor=actor or "web",
            detail={
                "passed": result["passed"],
                "review_status": result["review_status"],
                "replaced_case_id": result["replaced_case_id"],
            },
        )
        return result

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
        case = self.db.get_eval_case(case_id)
        if case is None:
            return None
        version = self.db.get_dataset_version(case["version_id"])
        if version and version.get("status") in {"frozen", "published"}:
            raise ValueError("frozen or published versions are read-only; create a draft first")
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
            auto_quality_status="pending",
            manual_review_status="pending",
            manual_review_by=None,
            manual_review_reason=None,
        )
        changed_fields = [
            field for field, value in {
                "question": question,
                "gold_answer": gold_answer,
                "type": type,
                "scope": scope,
                "difficulty": difficulty,
                "content_priority": content_priority,
                "must_have_points": must_have_points,
                "acceptable_answers": acceptable_answers,
                "evidence": evidence,
            }.items() if value is not None
        ]
        if hasattr(self.db, "save_audit"):
            self.db.save_audit(
                operation="dataset_case.edit",
                target_type="eval_case",
                target_id=str(case_id),
                actor="web",
                detail={"changed_fields": changed_fields},
            )
        return self.db.get_eval_case(case_id)

    def review_case(
        self,
        case_id: int,
        *,
        status: str,
        actor: str | None = None,
        reason: str | None = None,
    ) -> dict | None:
        case = self.db.get_eval_case(case_id)
        if case is None:
            return None
        version = self.db.get_dataset_version(case["version_id"])
        if version and version.get("status") != "draft":
            raise ValueError("冻结或发布版本不可修改人工审核状态，请先克隆草稿")
        if status == "approved" and case.get("auto_quality_status") != "passed":
            raise ValueError("自动质检未通过，不能人工确认")
        result = self.db.review_eval_case(case_id, status=status, actor=actor or "web", reason=reason)
        self.db.save_audit(
            operation="dataset_case.manual_review",
            target_type="eval_case",
            target_id=str(case_id),
            actor=actor or "web",
            detail={"status": status, "reason": (reason or "").strip()[:500]},
        )
        return result

    def check_draft_case(self, case_id: int) -> dict | None:
        case = self.db.get_eval_case(case_id)
        if case is None:
            return None
        version = self.db.get_dataset_version(case["version_id"])
        if not version or version.get("status") != "draft":
            raise ValueError("仅草稿题目可以执行自动质检")
        question_ok = bool(str(case.get("question") or "").strip())
        answer_ok = bool(str(case.get("gold_answer") or "").strip())
        status = "passed" if question_ok and answer_ok else "failed"
        reason = "问题和标准答案完整" if status == "passed" else "问题与标准答案均不能为空"
        self.db.update_eval_case(case_id, auto_quality_status=status, manual_review_status="pending")
        self.db.save_audit(
            operation="dataset_case.quality_check",
            target_type="eval_case",
            target_id=str(case_id),
            actor="web",
            detail={"status": status, "reason": reason},
        )
        return {"case_id": case_id, "auto_quality_status": status, "reason": reason, "case": self.db.get_eval_case(case_id)}

    def delete_case(self, case_id: int) -> bool:
        case = self.db.get_eval_case(case_id)
        if case is None:
            return False
        version = self.db.get_dataset_version(case["version_id"])
        if version and version.get("status") in {"frozen", "published"}:
            raise ValueError("frozen or published versions are read-only; create a draft first")
        self.db.retire_eval_case(case_id)
        self.db.update_dataset_version(case["version_id"], case_count=self.db.count_eval_cases(case["version_id"]))
        return True

    @staticmethod
    def _case_lineage_key(case: dict) -> str:
        """克隆版本沿用原 case id 尾段；外部题没有稳定 lineage 时退回题目键。"""
        uid = str(case.get("case_uid") or "")
        match = re.search(r"_(\d+)$", uid)
        return f"case:{int(match.group(1))}" if match else f"text:{str(case.get('question') or '').strip().lower()}"

    def version_diff(self, version_id: int) -> dict:
        version = self.db.get_dataset_version(version_id)
        if version is None:
            raise ValueError("version not found")
        parent_id = version.get("parent_version_id")
        if parent_id is None:
            return {"version_id": version_id, "parent_version_id": None, "added": [], "modified": [], "excluded": [], "counts": {"added": 0, "modified": 0, "excluded": 0}}
        current_cases = self.db.get_eval_cases(version_id, include_retired=True, limit=100000)
        parent_cases = self.db.get_eval_cases(parent_id, include_retired=False, limit=100000)
        current = {self._case_lineage_key(case): case for case in current_cases if not case.get("retired")}
        parent = {self._case_lineage_key(case): case for case in parent_cases}
        comparable_fields = ("question", "gold_answer", "evidence", "must_have_points", "acceptable_answers", "difficulty")
        modified = []
        for key in sorted(current.keys() & parent.keys()):
            if any(current[key].get(field) != parent[key].get(field) for field in comparable_fields):
                modified.append({"key": key, "before": parent[key], "after": current[key]})
        added = [{"key": key, "case": current[key]} for key in sorted(current.keys() - parent.keys())]
        excluded = [{"key": key, "case": parent[key]} for key in sorted(parent.keys() - current.keys())]
        return {
            "version_id": version_id,
            "parent_version_id": parent_id,
            "added": added,
            "modified": modified,
            "excluded": excluded,
            "counts": {"added": len(added), "modified": len(modified), "excluded": len(excluded)},
        }

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
        cases = self.db.get_eval_cases(version_id, include_retired=True, limit=100000)
        stats: dict[str, int] = {}
        active_cases = [case for case in cases if not case.get("retired")]
        for case in active_cases:
            for dim in ("difficulty", "content_priority", "type", "scope", "source"):
                key = case.get(dim) or "unknown"
                stats[f"{dim}:{key}"] = stats.get(f"{dim}:{key}", 0) + 1
        return {
            "total": len(active_cases),
            "retired": len(cases) - len(active_cases),
            "by_dimension": stats,
            "auto_quality": {
                "passed": sum(case.get("auto_quality_status") == "passed" for case in active_cases),
                "failed": sum(case.get("auto_quality_status") == "failed" for case in active_cases),
                "pending": sum(case.get("auto_quality_status") not in {"passed", "failed"} for case in active_cases),
            },
            "manual_review": {
                "approved": sum(case.get("manual_review_status") == "approved" for case in active_cases),
                "rejected": sum(case.get("manual_review_status") == "rejected" for case in active_cases),
                "pending": sum(case.get("manual_review_status") not in {"approved", "rejected"} for case in active_cases),
            },
        }

    # ------------------------------------------------------------------
    # 树形浏览（FR-DS-TREE-001）
    # ------------------------------------------------------------------
    def tree(self) -> dict:
        cases = self._publishable_cases()
        eius = self.db.list_eius(include_blocked=False)
        covered_eiu_ids = {
            case["eiu_id"]
            for case in cases
            if case.get("eiu_id") is not None
        }

        # section_path → 文档名 → 计数
        by_section: dict[str, dict] = {}
        for case in cases:
            eiu_id = case.get("eiu_id")
            eiu = next((e for e in eius if e.get("eiu_id") == eiu_id), None)
            path = (eiu or {}).get("section_path") or "未分类"
            doc = (eiu or {}).get("document_name") or "未关联文档"
            node = by_section.setdefault(
                path, {"section_path": path, "eiu_count": 0, "questionable_eiu_count": 0, "covered_eiu_count": 0, "case_count": 0, "coverage_pct": 0.0, "documents": {}}
            )
            node["documents"].setdefault(doc, 0)
            node["documents"][doc] += 1
            node["case_count"] += 1

        for eiu in eius:
            path = eiu.get("section_path") or "未分类"
            node = by_section.setdefault(
                path, {"section_path": path, "eiu_count": 0, "questionable_eiu_count": 0, "covered_eiu_count": 0, "case_count": 0, "coverage_pct": 0.0, "documents": {}}
            )
            node["eiu_count"] += 1
            if eiu.get("is_questionable"):
                node["questionable_eiu_count"] += 1
                if eiu.get("eiu_id") in covered_eiu_ids:
                    node["covered_eiu_count"] += 1
            node["documents"].setdefault(eiu.get("document_name") or "未关联文档", 0)

        tree_list = []
        for path, node in by_section.items():
            questionable_count = node["questionable_eiu_count"]
            node["coverage_pct"] = round(node["covered_eiu_count"] / questionable_count * 100, 1) if questionable_count else 0.0
            tree_list.append(
                {
                    "section_path": path,
                    "eiu_count": node["eiu_count"],
                    "case_count": node["case_count"],
                    "coverage_pct": node["coverage_pct"],
                    "gap": max(questionable_count - node["covered_eiu_count"], 0),
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
        self.db.update_job(job_id, phase="rebuild", progress=90, message="覆盖式整体重算中")
        self.db.update_job(
            job_id,
            status="done",
            phase="rebuild",
            progress=100,
            message="源文档产物已全量重算；已有冻结版本保持不变，请显式冻结创建新版本",
            finished=True,
        )

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
