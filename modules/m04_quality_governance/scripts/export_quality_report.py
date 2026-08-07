"""m04 质量门禁：导出质检报告（JSON / Markdown）。

用法：
  python -m modules.m04_quality_governance.scripts.export_quality_report \
      --corpus 1 [--out report.md] [--format md]

说明：基于已落库的检查结果生成汇总（不触发新一轮校验），
与 GET /api/corpus/{corpus_id}/quality-check/results 数据一致。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from modules.m04_quality_governance.services.pipeline import PipelineService
from modules.m04_quality_governance.services.prompts import CHECK_TYPE_DESCRIPTIONS
from modules.shared.core.logging_config import get_logger

logger = get_logger(__name__)


def build_report(corpus_id: int) -> dict:
    return PipelineService().get_results_summary(corpus_id)


def render_markdown(summary: dict) -> str:
    lines: list[str] = [
        f"# 质量校验报告（corpus {summary['corpus_id']}）",
        "",
        f"- 参与校验样本：{summary['total_cases']}",
        f"- 通过：{summary['passed']} / 失败：{summary['failed']}",
        "",
        "## 按检查项统计",
        "",
        "| 检查项 | 通过 | 失败 |",
        "| --- | ---: | ---: |",
    ]
    for check_type, stats in summary["by_check_type"].items():
        label = CHECK_TYPE_DESCRIPTIONS.get(check_type, check_type).split("：")[0]
        lines.append(f"| {label}（{check_type}） | {stats['passed']} | {stats['failed']} |")

    lines.append("")
    lines.append("## 失败样本")
    lines.append("")
    if not summary["failed_cases"]:
        lines.append("（无）")
    for failed in summary["failed_cases"]:
        lines.append(
            f"- case {failed['case_id']}：{', '.join(failed['failed_checks'])}"
        )
        lines.append(f"  - {failed['reason']}")

    if summary.get("errors"):
        lines.append("")
        lines.append("## 校验过程异常")
        lines.append("")
        for error in summary["errors"]:
            lines.append(f"- case {error['case_id']}：{error['error']}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="导出质量校验报告")
    parser.add_argument("--corpus", type=int, required=True, help="语料库 id")
    parser.add_argument(
        "--format", choices=["json", "md"], default="md", help="输出格式"
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="输出文件路径（默认打印到 stdout）",
    )
    args = parser.parse_args()

    summary = build_report(args.corpus)
    if args.format == "json":
        content = json.dumps(summary, ensure_ascii=False, indent=2)
    else:
        content = render_markdown(summary)

    if args.out:
        Path(args.out).write_text(content, encoding="utf-8")
        logger.info("质量报告已写入: %s", args.out)
    else:
        print(content)


if __name__ == "__main__":
    main()
