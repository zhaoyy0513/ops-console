from fastapi import FastAPI

from . import service
from .api import router


def register_module(app: FastAPI) -> None:
    """Redis 监控/受控操作模块（PRD §11，平台唯一可写外部资源）。"""
    app.include_router(router, prefix="/api")
    service.register_tester()
