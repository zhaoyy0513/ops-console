from fastapi import FastAPI

from .api import router


def register_module(app: FastAPI) -> None:
    """日志查看器模块：站点级日志源白名单 + SSH 字节窗口读取（只读）。"""
    app.include_router(router, prefix="/api")
