"""统一日志配置。

按工程规范（参考阿里巴巴 Java 开发手册「日志规约」精神）集中管理日志：
- 禁止在业务代码中使用 print 输出日志，统一通过 logging 模块。
- 生产环境默认 WARNING 级别，开发/调试可通过 LOG_LEVEL 环境变量调整。
- 统一格式包含时间、级别、模块、行号，便于问题排查。
"""
from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False

_DEFAULT_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str | None = None, *, force: bool = False) -> None:
    """配置根日志器。幂等：重复调用不会重复添加 handler（除非 force=True）。

    Args:
        level: 日志级别名称（DEBUG/INFO/WARNING/ERROR），默认读 LOG_LEVEL，
            未设置则为 WARNING。
        force: 为 True 时清空已有 handler 重新配置。
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    effective_level = (level or os.getenv("LOG_LEVEL", "WARNING")).upper()
    numeric = logging.getLevelName(effective_level)
    if not isinstance(numeric, int):
        effective_level = "WARNING"

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT, _DATE_FORMAT))

    root = logging.getLogger()
    if force:
        for existing in list(root.handlers):
            root.removeHandler(existing)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(effective_level)

    # 第三方库日志降噪，避免刷屏
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger。首次调用会触发根日志器配置。"""
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)
