from fastapi import FastAPI

from .api import router


def register_module(app: FastAPI) -> None:
    """知识库文档模块：Markdown 文档独立存储与 CRUD（不进站点资源抽屉）。"""
    app.include_router(router, prefix="/api")
