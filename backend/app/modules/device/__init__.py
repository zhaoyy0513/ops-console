"""Device 监控模块（原 robot，PRD §12，只读 HTTP 查询）。"""

from fastapi import FastAPI

from backend.app.core.redis import get_platform_redis

from . import service
from .api import router


def register_module(app: FastAPI) -> None:
    app.include_router(router, prefix="/api")
    service.register_tester()
    app.router.lifespan_context = _lifespan(app.router.lifespan_context)


def _lifespan(inner):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def ctx(app):
        async with inner(app):
            await migrate_robot_resource_keys()
            yield

    return ctx


async def migrate_robot_resource_keys() -> None:
    """robot→device 改名迁移（v1.0 预发布）：旧资源 hash ops:site:{id}:robots 一次性改名。

    幂等：目标 key 已存在（新代码已写入）则跳过；失败不阻断启动，下次启动重试。
    """
    try:
        r = get_platform_redis()
        async for key in r.scan_iter(match="ops:site:*:robots"):
            site_id = key.split(":")[2]
            new_key = f"ops:site:{site_id}:devices"
            if not await r.exists(new_key):
                await r.rename(key, new_key)
    except Exception:  # noqa: BLE001 - 迁移失败不阻断启动（redis 未就绪等），下次启动重试
        import loguru

        loguru.logger.warning("robot→device 资源 key 迁移失败，将在下次启动重试")
