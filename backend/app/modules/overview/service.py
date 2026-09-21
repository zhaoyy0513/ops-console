"""Overview 模块服务层：后台健康检查 + 站点聚合视图（PRD §7/§16）。"""

import json
import time
from datetime import datetime, timezone
from typing import Any

from backend.app.core import oplog
from backend.app.core.redis import get_platform_redis


def health_key(site_id: str) -> str:
    return f"ops:health:{site_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def check_site(site_id: str) -> int:
    """单站点全资源轻量检查，结果写平台 Redis hash。返回检查项数。

    # ponytail: 串行逐资源检查，10 资源约 10s；30s 间隔内够用，
    # 资源量大时换 asyncio.gather + 信号量
    """
    from backend.app.modules.mq.provider import ArtemisProvider
    from backend.app.modules.redis.provider import TargetRedisProvider
    from backend.app.modules.robot.provider import HttpRobotProvider
    from backend.app.modules.server.provider import SSHServerMetricsProvider
    from backend.app.modules.sites import service as sites_service

    entries: dict[str, str] = {}

    async def put(field: str, name: str, coro_factory, ok_status) -> None:
        try:
            result = await coro_factory()
        except Exception as e:  # noqa: BLE001 - 检查失败即 CRITICAL（不可达本身是异常）
            result = {"status": "CRITICAL", "message": str(e)[:120]}
        entries[field] = json.dumps(
            {"name": name, "checked_at": _now(), **result}, ensure_ascii=False
        )

    for cfg in await sites_service.list_resources(site_id, "servers", include_password=True):
        if not cfg.get("enabled", True):
            continue
        provider = SSHServerMetricsProvider(cfg)
        await put(f"server:{cfg['id']}", cfg["name"], provider.health_check, None)

    for cfg in await sites_service.list_resources(site_id, "redis", include_password=True):
        if not cfg.get("enabled", True):
            continue
        provider = TargetRedisProvider(cfg)

        async def redis_check(provider=provider):
            message = await provider.run_test()
            return {"status": "HEALTHY", "message": message}

        await put(f"redis:{cfg['id']}", cfg["name"], redis_check, None)

    for cfg in await sites_service.list_resources(site_id, "mq", include_password=True):
        if not cfg.get("enabled", True):
            continue
        provider = ArtemisProvider(cfg)

        async def mq_check(provider=provider):
            overview = await provider.get_overview()
            status = "HEALTHY" if overview.get("status") == "STARTED" else "WARNING"
            return {"status": status, "message": f"{overview.get('status')} {overview.get('version')}"}

        await put(f"mq:{cfg['id']}", cfg["name"], mq_check, None)

    for cfg in await sites_service.list_resources(site_id, "robots", include_password=True):
        if not cfg.get("enabled", True):
            continue
        provider = HttpRobotProvider(cfg)

        async def robot_check(provider=provider):
            message = await provider.run_test()
            return {"status": "HEALTHY", "message": message}

        await put(f"robot:{cfg['id']}", cfg["name"], robot_check, None)

    if entries:
        r = get_platform_redis()
        await r.delete(health_key(site_id))
        await r.hset(health_key(site_id), mapping=entries)
    return len(entries)


async def check_all_sites() -> None:
    from backend.app.modules.sites import service as sites_service

    for site in await sites_service.list_sites():
        if site.get("enabled", True):
            try:
                await check_site(site["id"])
            except Exception:  # noqa: BLE001 - 单站点失败不影响其他
                continue


async def get_overview(site_id: str) -> dict[str, Any]:
    """聚合视图（PRD §7）：各类型计数 + 异常摘要 + 最近 20 操作。"""
    from backend.app.modules.sites import service as sites_service

    site = await sites_service.get_site(site_id)
    if not site:
        from backend.app.modules.sites.service import NotFound

        raise NotFound(f"site not found: {site_id}")

    raw = await get_platform_redis().hgetall(health_key(site_id))
    items: list[dict[str, Any]] = []
    for field, payload in raw.items():
        kind, _, rid = field.partition(":")
        entry = json.loads(payload)
        entry.update({"kind": kind, "id": rid})
        items.append(entry)

    types = ("server", "redis", "mq", "robot")
    summary: dict[str, dict[str, int]] = {}
    for t in types:
        subset = [i for i in items if i["kind"] == t]
        summary[t] = {
            "total": len(subset),
            "healthy": sum(1 for i in subset if i["status"] == "HEALTHY"),
            "warning": sum(1 for i in subset if i["status"] == "WARNING"),
            "critical": sum(1 for i in subset if i["status"] == "CRITICAL"),
            "unknown": sum(1 for i in subset if i["status"] not in ("HEALTHY", "WARNING", "CRITICAL")),
        }

    order = {"CRITICAL": 3, "WARNING": 2, "UNKNOWN": 1}
    overall = "HEALTHY"
    for i in items:
        if order.get(i["status"], 0) > order.get(overall, 0):
            overall = i["status"]

    issues = sorted(
        (i for i in items if i["status"] != "HEALTHY"),
        key=lambda i: -order.get(i["status"], 0),
    )
    return {
        "site": site,
        "overall": overall,
        "summary": summary,
        "issues": issues,
        "recent_ops": await oplog.read_recent(20),
        "checked_at": max((i["checked_at"] for i in items), default=None),
    }
