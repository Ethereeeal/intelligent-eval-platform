"""m04 质量门禁：内部数据记录（dataclass）。

真实持久化模型位于 modules/shared/services/database.py（QualityCheckRow /
EvalCaseRow），此处仅定义服务层内部流转使用的轻量结构。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CheckItem:
    """单条质量检查结论（service 内部流转，落库前形态）。"""

    check_type: str
    passed: bool
    reason: str


@dataclass
class QualityReport:
    """单个 case 的一轮质量检查报告。"""

    case_id: int
    checks: list[CheckItem] = field(default_factory=list)
    # 失败分流后的标签（answer_coverage / generation_issue / None），由 pipeline 设置
    review_tag: str | None = None

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(item.passed for item in self.checks)

    @property
    def failed_checks(self) -> list[str]:
        return [item.check_type for item in self.checks if not item.passed]
