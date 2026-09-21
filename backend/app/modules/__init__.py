from fastapi import FastAPI

from backend.app.core import registry
from backend.app.modules import demo, sites

# 新增模块：import + 往元组加一行，其余文件零改动（PRD §24.2）
_MODULES = (sites, demo)


def register_all(app: FastAPI) -> None:
    registry.register_modules(app, _MODULES)
