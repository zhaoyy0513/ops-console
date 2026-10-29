from fastapi import FastAPI

from .api import router


def register_module(app: FastAPI) -> None:
    """依赖连通性矩阵：对站点已配置资源做后端出站 TCP 探测。"""
    app.include_router(router, prefix="/api")
