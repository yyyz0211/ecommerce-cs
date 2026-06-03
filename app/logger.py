"""Agent 日志模块。

项目当前只保留 Agent 相关日志，避免本地开发时被 API 请求日志淹没。
"""

import logging
import sys

LEVEL_NAMES = {
    logging.DEBUG: "调试",
    logging.INFO: "信息",
    logging.WARNING: "警告",
    logging.ERROR: "错误",
    logging.CRITICAL: "严重",
}


class ChineseFormatter(logging.Formatter):
    """把日志级别本地化为中文。"""

    def format(self, record: logging.LogRecord) -> str:
        record.level_zh = LEVEL_NAMES.get(record.levelno, record.levelname)
        return super().format(record)


# 日志格式：时间 | 级别 | 模块 | 消息
LOG_FORMAT = "%(asctime)s | %(level_zh)-2s | %(name)s | %(message)s"
DATE_FORMAT = "%m-%d %H:%M:%S"


def setup_logger(name: str) -> logging.Logger:
    """创建带统一中文格式的 logger。"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(ChineseFormatter(LOG_FORMAT, DATE_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def configure_agent_only_logging() -> None:
    """关闭本地开发中常见的非 Agent 噪声日志。"""
    logging.getLogger().setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


# 只保留 Agent 日志实例
agent_logger = setup_logger("agent")
