"""Robot 模块服务层（PRD §12）：列表/详情 + 连接测试，5s 缓存。"""

import time
from typing import Any

from backend.app.core.cache import cached
from backend.app.modules.robot.provider import HttpRobotProvider
from backend.app.modules.sites.service import NotFound
from backend.app.shared import testconn
from backend.app.shared.concurrency import get_semaphore
from backend.app.shared.errors import OpsError

CACHE_TTL = 5  # PRD §14


def _build_provider(config: dict[str, Any]) -> HttpRobotProvider:
    return HttpRobotProvider(config)


async def _require_robot_config(site_id: str, robot_id: str) -> dict[str, Any]:
    from backend.app.modules.sites import service as sites_service

    config = await sites_service.get_resource_raw(site_id, "robots", robot_id)
    if not config:
        raise NotFound(f"robot instance not found: {robot_id}")
    return config


async def list_robots(site_id: str, robot_id: str) -> list[dict[str, Any]]:
    config = await _require_robot_config(site_id, robot_id)
    provider = _build_provider(config)

    async def factory():
        async with get_semaphore("robot"):
            return await provider.get_robot_list()

    return await cached(f"ops:cache:robot:{robot_id}:status", CACHE_TTL, factory)


async def get_robot(site_id: str, robot_id: str, rid: str) -> dict[str, Any]:
    config = await _require_robot_config(site_id, robot_id)
    provider = _build_provider(config)

    async def factory():
        async with get_semaphore("robot"):
            return await provider.get_robot_detail(rid)

    return await cached(f"ops:cache:robot:{robot_id}:detail:{rid}", CACHE_TTL, factory)


async def robot_tester(config: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    provider = _build_provider(config)
    async with get_semaphore("robot"):
        message = await provider.run_test()
    return {
        "success": True,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "message": message,
    }


def register_tester() -> None:
    testconn.register_tester("robot", robot_tester)


__all__ = ["list_robots", "get_robot", "robot_tester", "register_tester", "OpsError"]
