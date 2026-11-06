"""
统一日志（loguru）
- 控制台 INFO+
- 文件 app.log（每日切割，保留 30 天，gz 压缩）
- 文件 llm.log（LLM 调用专用 channel，便于排查模型问题）

日志目录优先级（自上而下）：
  1. 环境变量 LOG_DIR
  2. settings.LOG_DIR（来自 .env）
  3. backend/logs（项目内兜底，确保任何环境都能起服务）

避免硬编码 /var/log/repair-system（V11 上需要 sudo 才能建）
"""
import sys
import os
from pathlib import Path

from loguru import logger


# 移除默认 handler
logger.remove()

# 控制台
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
           "<level>{level: <8}</level> | "
           "<cyan>{name}</cyan> - {message}",
    colorize=True,
)


def _resolve_log_dir() -> Path:
    """按优先级解析日志目录，并保证可写"""
    candidates = []

    # 1) 环境变量
    if os.environ.get("LOG_DIR"):
        candidates.append(os.environ["LOG_DIR"])

    # 2) settings.LOG_DIR （延迟 import 避免循环依赖）
    try:
        from app.config import settings
        candidates.append(settings.LOG_DIR)
    except Exception:
        pass

    # 3) 项目内兜底
    candidates.append(str(Path(__file__).resolve().parents[2] / "logs"))

    for path in candidates:
        try:
            p = Path(path)
            p.mkdir(parents=True, exist_ok=True)
            # 写权限测试
            test_file = p / ".write_test"
            test_file.touch()
            test_file.unlink()
            return p
        except (PermissionError, OSError):
            continue

    # 全部失败 → 用 /tmp（永远可写）
    fallback = Path("/tmp/repair-system-logs")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


log_dir = _resolve_log_dir()

# 应用日志
logger.add(
    log_dir / "app.log",
    rotation="00:00",
    retention="30 days",
    compression="gz",
    level="INFO",
    enqueue=True,
)

# LLM 专用 channel
logger.add(
    log_dir / "llm.log",
    rotation="00:00",
    retention="14 days",
    compression="gz",
    level="INFO",
    enqueue=True,
    filter=lambda r: r["extra"].get("channel") == "llm",
)

llm_logger = logger.bind(channel="llm")

logger.info(f"日志目录: {log_dir}")
