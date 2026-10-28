from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import router
from .service import migrate_legacy_pages


def register_module(app: FastAPI) -> None:
    """站点 + 资源配置管理模块（PRD §5/§6/§18）。"""
    app.include_router(router, prefix="/api")
    app.router.lifespan_context = _lifespan(app.router.lifespan_context)


def _lifespan(inner):
    """启动时跑一次 pages→knowledge 迁移（幂等）。新版 FastAPI 已移除
    add_event_handler，沿用 overview/ssh 模块的 lifespan 包裹模式；
    迁移失败不阻断启动（redis 未就绪等），下次启动重试。"""

    @asynccontextmanager
    async def ctx(app):
        try:
            await migrate_legacy_pages()
        except Exception:  # noqa: BLE001 - 同 device 模块迁移：失败不阻断启动
            import loguru

            loguru.logger.warning("pages→knowledge 资源 key 迁移失败，将在下次启动重试")
        async with inner(app):
            yield

    return ctx
