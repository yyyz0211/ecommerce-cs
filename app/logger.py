"""统一日志模块"""

import logging
import sys

# 日志格式：时间 | 级别 | 模块 | 消息
LOG_FORMAT = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
DATE_FORMAT = "%m-%d %H:%M:%S"

def setup_logger(name: str) -> logging.Logger:
    """创建带统一格式的 logger"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

# 各模块 logger 实例
db_logger = setup_logger("db")
api_logger = setup_logger("api")
agent_logger = setup_logger("agent")
error_logger = setup_logger("error")
