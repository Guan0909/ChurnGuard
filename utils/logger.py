"""统一日志模块 —— 基于 loguru 封装"""

import sys
from pathlib import Path

from loguru import logger

from config import settings


def setup_logger() -> None:
    """初始化全局日志配置"""
    logger.remove()  # 移除默认 handler

    # 控制台输出
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 文件输出（按日轮转）
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir / "churnguard_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )


def get_logger(name: str = __name__):
    """获取 logger 实例（兼容旧接口，实际返回 loguru logger）"""
    return logger.bind(module=name)


# 模块加载时自动初始化
setup_logger()