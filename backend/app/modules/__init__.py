from fastapi import FastAPI

from backend.app.core import registry
from backend.app.modules import audit, database, device, knowledge, logs, mq, netdiag, overview, redis, server, ssh, sites, testconn

# 新增模块：import + 往元组加一行，其余文件零改动（PRD §24.2）
_MODULES = (sites, knowledge, logs, testconn, server, redis, mq, device, overview, audit, ssh, database, netdiag)


def register_all(app: FastAPI) -> None:
    registry.register_modules(app, _MODULES)
