from fastapi import FastAPI

from .api import router


def register_module(app: FastAPI) -> None:
    """操作日志查询模块（PRD §17）。"""
    app.include_router(router, prefix="/api")
