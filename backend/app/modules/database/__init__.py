"""数据库监控 demo 模块（验收 18）：仅新增目录 + 一行注册，验证扩展机制。"""

from fastapi import FastAPI

from .api import router


def register_module(app: FastAPI) -> None:
    app.include_router(router, prefix="/api")
