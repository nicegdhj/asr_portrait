"""
日志配置模块

统一管理应用日志输出
"""

import sys
from pathlib import Path

from loguru import logger

from src.core.config import settings


def setup_logging():
    """
    配置日志系统

    - 本地开发: 控制台 + 文件
    - 生产环境: 仅文件
    - 日志格式: 时间(秒级) | 级别 | 位置 - 消息
    - 日志轮转: 基于文件大小 (100MB)
    """

    # 移除默认handler
    logger.remove()

    # 创建日志目录
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # 日志格式 (标准化)
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    file_format = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"

    # 1. 控制台输出 (仅开发环境)
    if settings.debug:
        logger.add(
            sys.stderr,
            level=settings.log_level,
            format=log_format,
            colorize=True,
        )

    # 2. 文件输出 - 所有日志 (固定文件名)
    logger.add(
        "logs/portrait.log",
        level="DEBUG",
        format=file_format,
        rotation="100 MB",  # 基于大小轮转 (100MB)
        retention=5,  # 保留最近5个备份文件
        compression="zip",  # 压缩旧日志
        encoding="utf-8",
        enqueue=True,  # 异步写入
    )

    # 3. 文件输出 - 仅错误日志 (固定文件名)
    logger.add(
        "logs/error.log",
        level="ERROR",
        format=file_format,
        rotation="50 MB",  # 错误日志轮转阈值更小
        retention=10,  # 错误日志保留更多备份
        compression="zip",
        encoding="utf-8",
        enqueue=True,
    )

    logger.info("日志系统初始化完成")
    logger.info(f"日志目录: {log_dir.absolute()}")
    logger.info(f"日志级别: {settings.log_level}")
    logger.info(f"调试模式: {settings.debug}")
