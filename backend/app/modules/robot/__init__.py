from fastapi import FastAPI

from . import service
from .api import router


def register_module(app: FastAPI) -> None:
    """Robot 监控模块（PRD §12，只读 HTTP 查询）。"""
    app.include_router(router, prefix="/api")
    service.register_tester()
