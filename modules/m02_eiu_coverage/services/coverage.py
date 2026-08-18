"""M02 — 覆盖规划（确定性代码，不依赖 LLM，SPEC §6，按文件维度，无 corpus）。

包含：加权覆盖率计算（§6.1）、覆盖率失真防护告警（§6.2）、
业务门禁数据（§6.3）、实质 Block 对账（§6.4）。
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from modules.shared.services.database import PRIORITY_WEIGHT, DatabaseService

# 覆盖统计口径：仅统计达到可发布态的 generated_case（与 m05 PUBLISHABLE_STATUSES 一致），
# candidate / blocked / needs_revision 不计入"已覆盖"，避免抬高覆盖率通过门禁。
PUBLISHABLE_STATUSES = {
    "quality_verified",
    "governance_passed",
    "user_confirmed",
    "published",
}


def _default_covered_eiu_ids(database: DatabaseService) -> set[int]:
    """默认已覆盖集合：已生成且处于可发布态样本的 EIU id（BRD c_i=1 口径）。"""
    return database.list_covered_eiu_ids(statuses=PUBLISHABLE_STATUSES)


def save_coverage_report(
    *,
    covered_eiu_ids: Iterable[int] | None = None,
    blocked_eiu_ids: Iterable[int] | None = None,
    snapshot_metadata: dict | None = None,
) -> int:
    """计算覆盖率并落库为一条 coverage_report，返回 report_id（供 m05 冻结外键引用）。"""
    report = compute_coverage(
        covered_eiu_ids=covered_eiu_ids, blocked_eiu_ids=blocked_eiu_ids
    )
    return DatabaseService().save_coverage_report(
        total_eiu=report["total_eiu"],
        questionable_eiu=report["questionable_eiu"],
        excluded_eiu=report["excluded_eiu"],
        by_priority=report["by_priority"],
        by_type=report["by_type"],
        by_document=report["by_document"],
        by_section=report["by_section"],
        weighted_coverage=report["weighted_coverage"],
        p0_coverage_pct=report["p0_coverage_pct"],
        block_reconciliation=report["block_reconciliation"],
        alerts=report["alerts"],
        snapshot_metadata=snapshot_metadata,
    )


def compute_coverage(
    *,
    covered_eiu_ids: Iterable[int] | None = None,
    blocked_eiu_ids: Iterable[int] | None = None,
) -> dict:
    """生成覆盖率报告（全库维度，按文件组织 by_document 的确定性计算）。

    covered_eiu_ids：已有通过质量校验题目的 EIU（M03 生成题目后传入；M02 阶段为空，
    weighted_coverage 相应为 0.0，见 SPEC §7.3 示例）。
    blocked_eiu_ids：DELETE 软删除的 EIU（不计入分母）。

    未显式传入 covered_eiu_ids 时，自动取"已生成且处于可发布态"样本的 EIU 集合，
    保证 /api/eiu/coverage 与 m05 冻结时落库的覆盖率不是恒 0。
    """
    database = DatabaseService()
    covered: set[int] = (
        set(covered_eiu_ids) if covered_eiu_ids is not None else _default_covered_eiu_ids(database)
    )
    blocked: set[int] = set(blocked_eiu_ids or [])

    eius = database.list_eius(include_blocked=False)
    blocks = database.list_blocks()

    # ---- 基础计数（blocked 已由 list_eius 过滤）----
    active = [eiu for eiu in eius if eiu["eiu_id"] not in blocked]
    questionable = [eiu for eiu in active if eiu["is_questionable"]]
    excluded = [eiu for eiu in active if not eiu["is_questionable"]]

    # ---- 多维统计 ----
    by_priority: dict[str, int] = dict(Counter(eiu["content_priority"] for eiu in active))
    by_type: dict[str, int] = dict(Counter(eiu["eiu_type"] for eiu in active))

    by_document_counter: dict[int, int] = Counter()
    by_section_counter: dict[str, int] = Counter()
    for eiu in active:
        if eiu["document_id"] is not None:
            by_document_counter[eiu["document_id"]] += 1
        if eiu["section_path"]:
            by_section_counter[eiu["section_path"]] += 1
    document_names = {
        document["document_id"]: document["file_name"]
        for document in database.list_documents()
    }
    by_document = [
        {
            "document_id": document_id,
            "document_name": document_names.get(document_id),
            "eiu_count": count,
        }
        for document_id, count in sorted(by_document_counter.items())
    ]
    by_section = [
        {"section_path": section_path, "eiu_count": count}
        for section_path, count in sorted(by_section_counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    # ---- 加权覆盖率（分母仅含 is_questionable=true，SPEC §6.1）----
    total_weight = 0
    covered_weight = 0
    p0_total = 0
    p0_covered = 0
    for eiu in questionable:
        weight = eiu["weight"] or PRIORITY_WEIGHT.get(eiu["content_priority"], 1)
        total_weight += weight
        if eiu["content_priority"] == "P0":
            p0_total += 1
        if eiu["eiu_id"] in covered:
            covered_weight += weight
            if eiu["content_priority"] == "P0":
                p0_covered += 1

    weighted_coverage = covered_weight / total_weight if total_weight > 0 else 0.0
    p0_coverage_pct = p0_covered / p0_total if p0_total > 0 else 1.0

    # ---- 实质 Block 对账（SPEC §6.4；标题块不参与）----
    paragraph_blocks = [block for block in blocks if block["block_type"] != "title"]
    covered_block_ids = {eiu["block_id"] for eiu in active}
    uncovered_blocks = [
        block for block in paragraph_blocks if block["block_id"] not in covered_block_ids
    ]
    total_paragraph = len(paragraph_blocks)
    covered_blocks = len(covered_block_ids)
    reconciliation_rate = covered_blocks / total_paragraph if total_paragraph > 0 else 1.0

    # ---- 失真防护告警（SPEC §6.2）----
    alerts: list[str] = []
    active_total = len(active)
    if active_total > 0 and len(excluded) / active_total > 0.5:
        alerts.append(
            f"排除记录占比 {len(excluded) / active_total:.0%} 超过 50%，"
            "疑似覆盖率分母被人为排空，请检查 exclusion_reason"
        )
    for eiu in excluded:
        if "难生成" in (eiu["exclusion_reason"] or "") or "难出题" in (eiu["exclusion_reason"] or ""):
            alerts.append(
                f"EIU {eiu['eiu_id']} 的排除原因不合理（{eiu['exclusion_reason']}），"
                "不得因'题目难生成'排除"
            )
            break
    if total_paragraph > 0 and reconciliation_rate < 1.0:
        alerts.append(
            f"实质 Block 对账率 {reconciliation_rate:.0%} < 100%，"
            f"有 {len(uncovered_blocks)} 个段落未生成 EIU 或排除记录"
        )

    return {
        "total_eiu": len(active),
        "questionable_eiu": len(questionable),
        "excluded_eiu": len(excluded),
        "by_priority": {priority: by_priority.get(priority, 0) for priority in ("P0", "P1", "P2")},
        "by_type": by_type,
        "by_document": by_document,
        "by_section": by_section,
        "weighted_coverage": round(weighted_coverage, 4),
        "p0_coverage_pct": round(p0_coverage_pct, 4),
        "block_reconciliation": {
            "total_paragraph_blocks": total_paragraph,
            "covered_blocks": covered_blocks,
            "rate": round(reconciliation_rate, 4),
            "uncovered_blocks": [
                {"block_id": block["block_id"], "section_path": block["section_path"]}
                for block in uncovered_blocks
            ],
        },
        "alerts": alerts,
    }


def compute_gaps(*, covered_eiu_ids: Iterable[int] | None = None) -> list[dict]:
    """未覆盖 EIU 清单：可出题但尚无对应题目的 EIU（M02 阶段即全部可出题项）。"""
    database = DatabaseService()
    covered: set[int] = (
        set(covered_eiu_ids) if covered_eiu_ids is not None else _default_covered_eiu_ids(database)
    )
    eius = database.list_eius(include_blocked=False)
    gaps = [
        {
            "eiu_id": eiu["eiu_id"],
            "block_id": eiu["block_id"],
            "section_path": eiu["section_path"],
            "statement": eiu["statement"],
            "eiu_type": eiu["eiu_type"],
            "content_priority": eiu["content_priority"],
            "weight": eiu["weight"],
            "reason": "暂无对应题目",
        }
        for eiu in eius
        if eiu["is_questionable"] and eiu["eiu_id"] not in covered
    ]
    return gaps


def assert_coverage_gate(report: dict) -> None:
    """发布门禁（m05 freeze 强制执行，BRD FR-COVER-002 / README §3.3）：

    - 总体加权 EIU 覆盖率 < 85% → 阻断发布；
    - P0 EIU 覆盖率 < 100% → 阻断发布；
    - 实质 Block 对账率 < 100% → 阻断发布。
    不达标抛出 ValueError（上层转为 400）。
    """
    failures: list[str] = []
    weighted = report.get("weighted_coverage")
    if weighted is not None and weighted < 0.85:
        failures.append(f"总体加权 EIU 覆盖率 {weighted:.1%} < 85%，未达到发布门禁")
    p0 = report.get("p0_coverage_pct")
    if p0 is not None and p0 < 1.0:
        failures.append(f"P0 EIU 覆盖率 {p0:.1%} < 100%，未达到发布门禁")
    reconciliation = (report.get("block_reconciliation") or {}).get("rate")
    if reconciliation is not None and reconciliation < 1.0:
        failures.append(
            f"实质 Block 对账率 {reconciliation:.1%} < 100%，存在未关联 EIU/排除记录的文段"
        )
    if failures:
        raise ValueError("；".join(failures))
