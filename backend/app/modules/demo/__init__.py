from fastapi import FastAPI

from .api import router


def register_module(app: FastAPI) -> None:
    """演示模块注册契约（PRD §24.1），作为后续模块的模板。"""
    app.include_router(router, prefix="/api")
