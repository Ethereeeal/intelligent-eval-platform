"""导出评测样本集（README §2.6 输出模式 B — 问答对集）。

用法：
    python -m modules.m03_generation.scripts.export_cases \
        --corpus 1 --format json --out eval_cases.json

format 支持:
    json  — 完整结构（含证据绑定），可直接作为评测集交付物
    md    — 人类可读的 Markdown 清单（题目/答案/难度/优先级/章节定位）
"""
from __future__ import annotations

import argparse
import json

from modules.shared.core.logging_config import get_logger
from modules.shared.services.database import DatabaseService

logger = get_logger(__name__)


def export_json(cases: list[dict]) -> str:
    return json.dumps(
        {
            "exported_at": None,
            "count": len(cases),
            "cases": cases,
        },
        ensure_ascii=False,
        indent=2,
    )


def export_markdown(cases: list[dict]) -> str:
    lines = ["# 评测样本集\n"]
    for case in cases:
        evidence = case.get("evidence") or []
        first = evidence[0]["evidence"] if evidence else {}
        lines.append(f"## {case['case_id']} · {case['question']}")
        lines.append(f"- 题型: {case['question_type']} / 难度: {case['difficulty']} "
                     f"/ 优先级: {case['content_priority']} / 状态: {case['review_status']}")
        lines.append(f"- 标准答案: {case['gold_answer']}")
        points = case.get("must_have_points") or []
        if points:
            lines.append("- 必须命中要点:")
            for point in points:
                lines.append(f"  - {point}")
        if first:
            lines.append(f"- 证据定位: {first.get('section_path', '未分类')} "
                         f"page {first.get('page_no') or '?'} "
                         f"(block {first.get('block_id')}) {first.get('document_name', '')}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="导出评测样本集")
    parser.add_argument("--corpus", type=int, required=True, help="语料库 ID")
    parser.add_argument("--format", choices=["json", "md"], default="json")
    parser.add_argument("--out", default="eval_cases.json", help="输出文件路径")
    parser.add_argument("--difficulty", help="按难度过滤: L1/L2/L3")
    parser.add_argument("--status", help="按状态过滤: candidate/quality_verified/...")
    args = parser.parse_args()

    database = DatabaseService()
    cases = database.list_generated_cases(
        args.corpus,
        difficulty=args.difficulty,
        status=args.status,
    )
    content = export_markdown(cases) if args.format == "md" else export_json(cases)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(content)
    logger.info("已导出 %d 条评测样本 -> %s", len(cases), args.out)


if __name__ == "__main__":
    main()
