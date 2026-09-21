"""Overview 模块：30 秒后台健康检查 + 站点聚合 API（PRD §7/§16）。"""

from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .api import router
from . import service

# ponytail: 单实例假设，多实例部署需分布式锁防重复检查
_scheduler: AsyncIOScheduler | None = None


def register_module(app: FastAPI) -> None:
    app.include_router(router, prefix="/api")
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        _scheduler.add_job(service.check_all_sites, "interval", seconds=30, id="site-health-check")
        app.router.lifespan_context = _lifespan(app.router.lifespan_context)


def _lifespan(inner):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def ctx(app):
        async with inner(app):
            _scheduler.start()
            try:
                yield
            finally:
                if _scheduler.running:
                    _scheduler.shutdown(wait=False)

    return ctx
