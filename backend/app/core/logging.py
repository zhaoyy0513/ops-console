"""应用日志（PRD §29）：Loguru + rotation/retention + 请求关联字段。"""

import sys
import uuid

from loguru import logger

_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[request_id]} | "
    "{extra[site_id]} | {extra[resource_id]} | {name}:{line} | {message}"
)


def setup_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.configure(extra={"request_id": "-", "site_id": "-", "resource_id": "-"})
    logger.add(sys.stderr, level=level, format=_FORMAT)
    logger.add("logs/app/app.log", level=level, rotation="10 MB", retention="7 days",
               encoding="utf-8", format=_FORMAT)
    logger.add("logs/error/error.log", level="ERROR", rotation="10 MB", retention="30 days",
               encoding="utf-8", format=_FORMAT)


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]
