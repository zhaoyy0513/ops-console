from fastapi import FastAPI

from .api import router


def register_module(app: FastAPI) -> None:
    """连接测试分发端点（PRD §13/§18），具体 tester 由各资源模块注册。"""
    app.include_router(router, prefix="/api")
