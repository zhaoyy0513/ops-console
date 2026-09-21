from fastapi import FastAPI

from .api import router


def register_module(app: FastAPI) -> None:
    """站点 + 资源配置管理模块（PRD §5/§6/§18）。"""
    app.include_router(router, prefix="/api")
