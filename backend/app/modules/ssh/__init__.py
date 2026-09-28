"""SSH 脚本模块：绑定 Server 的脚本管理、手动执行与 cron 定时调度。"""

from fastapi import FastAPI

from . import scheduling
from .api import router


def register_module(app: FastAPI) -> None:
    app.include_router(router, prefix="/api")
    scheduling.attach_scheduler(app)  # cron 定时调度 + 启动恢复
