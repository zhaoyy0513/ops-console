"""SSH 脚本模块：绑定 Server 的脚本管理与受控执行。"""

from fastapi import FastAPI

from .api import router


def register_module(app: FastAPI) -> None:
    app.include_router(router, prefix="/api")
