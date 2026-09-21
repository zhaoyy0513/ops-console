"""MQ 模块：Jolokia provider + 诊断 + backlog 趋势采样（PRD §9）。"""

from fastapi import FastAPI

from . import service
from .api import router

# ponytail: 采样 job 由模块自启，单实例假设；多实例部署需分布式锁防重复采样
from apscheduler.schedulers.asyncio import AsyncIOScheduler

_scheduler: AsyncIOScheduler | None = None


async def _sample_backlogs() -> None:
    """周期采样全部站点的 MQ 队列 backlog（get_queues 内部自动 push_sample）。"""
    from backend.app.modules.sites import service as sites_service

    for site in await sites_service.list_sites():
        for mq in await sites_service.list_resources(site["id"], "mq"):
            if not mq.get("enabled", True):
                continue
            try:
                await service.get_queues(site["id"], mq["id"])
            except Exception:  # noqa: BLE001 - 单个实例失败不影响其他采样
                continue


def register_module(app: FastAPI) -> None:
    app.include_router(router, prefix="/api")
    service.register_tester()
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        _scheduler.add_job(_sample_backlogs, "interval", seconds=60, id="mq-backlog-sampling")
        # AsyncIOScheduler 需要 running loop，挂到应用生命周期启动（仍在模块内，不改 main.py）
        app.router.lifespan_context = _lifespan_with_scheduler(app.router.lifespan_context)


def _lifespan_with_scheduler(inner):
    """包装应用原 lifespan：启动时开采样调度器，关闭时停掉。"""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def ctx(app):
        async with inner(app):
            await _start_scheduler()
            try:
                yield
            finally:
                await _stop_scheduler()

    return ctx


async def _start_scheduler() -> None:
    if _scheduler is not None:
        _scheduler.start()


async def _stop_scheduler() -> None:
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
