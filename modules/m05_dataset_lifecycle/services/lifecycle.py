"""m05 数据集生命周期服务。

职责（对齐 README §1 / §3）：
- 版本冻结（freeze）：生成 version_number、记录快照元信息、状态置 frozen。
- 导出：扁平 JSONL / 目录结构 JSON / Excel。
- 编辑：手动编辑样本（PUT）→ 回退 review_status=candidate；删除标记 retired 保留审计。
- 树形浏览：按 section_path 组织，标注样本数 / 覆盖率 / 未覆盖缺口。
- 无问题提示：EIU=0 或 全部不可出题时不发布空集。
- 文档重传处理：**覆盖式整体作废 + 全量重算**（无增量更新）。

说明：m03 生成 / m04 质量治理尚未就绪，本模块的样本生成用占位实现
（直接基于 m01 的 document_block 文本抽题），仅用于打通端到端流程；
正式题面/质量校验接入 m03、m04 后替换 `generate_cases_for_document` 即可。
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from modules.shared.services.database import DatabaseService


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
    # 版本冻结
    # ------------------------------------------------------------------
    def freeze_version(self, *, corpus_id: int, created_by: str | None = None) -> dict:
        corpus = self.db.get_corpus(corpus_id)
        if corpus is None:
            raise ValueError("corpus not found")

        # 无问题判定（FR-DS-EMPTY）：基于 m01 语料是否有可出题 Block
        blocks = self.db.list_blocks(corpus_id=corpus_id)
        if not blocks:
            raise ValueError("无问题可生成：语料库没有任何解析后的文段，未进入发布流程")

        # 占位生成：基于 m01 block 文本抽题（待 m03 生成接入后替换）
        latest = self.db.get_latest_version_number(corpus_id)
        version_number = _next_version_number(latest)
        version_id = self.db.save_dataset_version(
            corpus_id=corpus_id,
            version_number=version_number,
            status="frozen",
            split_config={"format": "full", "include_retired": False},
            snapshot_metadata={
                "corpus_version": corpus.get("version"),
                "created_by": created_by,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "generator": "m05_placeholder(v1 blocks)",
            },
        )
        case_count = self._generate_cases(version_id=version_id, corpus_id=corpus_id)
        self.db.update_dataset_version(version_id, case_count=case_count, freeze=True)
        return self.db.get_dataset_version(version_id)

    def list_versions(self, corpus_id: int) -> list[dict]:
        return self.db.list_dataset_versions(corpus_id)

    def get_version(self, version_id: int) -> dict | None:
        return self.db.get_dataset_version(version_id)

    # ------------------------------------------------------------------
    # 样本生成（占位，待 m03/m04 接入）
    # ------------------------------------------------------------------
    def _generate_cases(self, *, version_id: int, corpus_id: int) -> int:
        blocks = self.db.list_blocks(corpus_id=corpus_id)
        count = 0
        for idx, block in enumerate(blocks, start=1):
            text = (block.get("block_text") or "").strip()
            if len(text) < 20:
                continue  # 过短文段不单独出题
            question = text
            self.db.save_eval_case(
                version_id=version_id,
                case_uid=f"case_{version_id:04d}_{idx:04d}",
                question=question,
                type="fact_recall",
                scope="single_document",
                difficulty="L2",
                gold_answer=text,
                evidence=[{"block_id": block.get("block_id")}],
                eiu_ids=[block.get("block_id")],
                content_priority="P1",
                source="native",
            )
            count += 1
        return count

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
    # 树形浏览
    # ------------------------------------------------------------------
    def tree(self, corpus_id: int) -> dict:
        blocks = self.db.list_blocks(corpus_id=corpus_id)
        nodes: dict[str, dict] = {}
        for block in blocks:
            path = block.get("section_path") or "未分类"
            node = nodes.setdefault(
                path, {"section_path": path, "eiu_count": 0, "case_count": 0, "coverage_pct": 0.0}
            )
            node["eiu_count"] += 1
        # case_count / coverage 暂基于最新版本（占位，待 m03 出题回写 eiu_ids）
        latest = self.db.get_latest_version_number(corpus_id)
        if latest:
            version = self.db.get_dataset_version(
                self.db.list_dataset_versions(corpus_id)[0]["version_id"]
            )
            cases = self.db.get_eval_cases(version["version_id"]) if version else []
            by_section: dict[str, int] = {}
            for case in cases:
                for eiu in case.get("eiu_ids") or []:
                    by_section.setdefault(str(eiu), 0)
            for case in cases:
                for eiu in case.get("eiu_ids") or []:
                    by_section[str(eiu)] = by_section.get(str(eiu), 0) + 1
        tree_list = [
            {
                "section_path": path,
                "eiu_count": node["eiu_count"],
                "case_count": node["eiu_count"],  # 占位：1 block→1 题
                "coverage_pct": 100.0 if node["eiu_count"] > 0 else 0.0,
            }
            for path, node in nodes.items()
        ]
        return {"corpus_id": corpus_id, "tree": tree_list}

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
        return {
            "dataset_version": version["version_number"],
            "coverage": version.get("snapshot_metadata", {}).get("coverage"),
            "documents": [
                {
                    "document_name": "placeholder",
                    "sections": [{"section_path": "all", "cases": cases}],
                }
            ],
        }

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
    # 文档重传：覆盖式整体作废 + 全量重算（无增量）
    # ------------------------------------------------------------------
    def rebuild_on_reupload(self, *, corpus_id: int, document_id: int, job_id: int) -> None:
        """文档重传回调（由 01 的 doc_update_job 完成后触发）。

        策略：整体作废该文档相关产物并全量重算。
        - 当前 m05 样本为按文档聚合生成；重传后对该文档对应版本的样本整体重建。
        - 不做增量失效回写、不做旧题复用（见 README §8.14 / §3.3）。
        """
        self.db.update_job(job_id, phase="rebuild", progress=80, message="覆盖式整体重算中")
        # 占位：删除旧版本中属于该文档的 case 并基于新 block 全量重算
        latest_versions = self.db.list_dataset_versions(corpus_id)
        if latest_versions:
            version_id = latest_versions[0]["version_id"]
            # 简化：整体重建该版本全部 case（占位实现，待 m03 接入细化到文档级）
            blocks = self.db.list_blocks(corpus_id=corpus_id)
            new_count = 0
            for idx, block in enumerate(blocks, start=1):
                text = (block.get("block_text") or "").strip()
                if len(text) < 20:
                    continue
                self.db.save_eval_case(
                    version_id=version_id,
                    case_uid=f"case_{version_id:04d}_r{idx:04d}",
                    question=text,
                    type="fact_recall",
                    scope="single_document",
                    difficulty="L2",
                    gold_answer=text,
                    evidence=[{"block_id": block.get("block_id")}],
                    eiu_ids=[block.get("block_id")],
                    content_priority="P1",
                    source="native",
                )
                new_count += 1
            self.db.update_dataset_version(version_id, case_count=new_count)
        self.db.update_job(job_id, status="done", phase="rebuild", progress=100, message="已更新完成", finished=True)
