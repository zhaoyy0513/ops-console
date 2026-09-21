from fastapi import FastAPI

from . import service
from .api import router


def register_module(app: FastAPI) -> None:
    """Server 只读诊断模块（PRD §8）：注册路由 + 连接测试器。"""
    app.include_router(router, prefix="/api")
    service.register_tester()
