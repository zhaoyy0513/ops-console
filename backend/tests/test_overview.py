import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.modules.overview import service


@pytest.fixture
async def client(fake_platform_redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/sites", json={"id": "sz", "name": "S"})
        yield c


async def _set_health(redis, site_id: str, entries: dict):
    await redis.hset(f"ops:health:{site_id}", mapping={
        k: json.dumps(v) for k, v in entries.items()
    })


async def test_overview_counts_and_overall(client, fake_platform_redis):
    await _set_health(fake_platform_redis, "sz", {
        "server:s1": {"name": "s1", "status": "HEALTHY", "message": "ok", "checked_at": "2026-09-21T00:00:00+00:00"},
        "server:s2": {"name": "s2", "status": "WARNING", "message": "cpu 85%", "checked_at": "2026-09-21T00:00:00+00:00"},
        "redis:r1": {"name": "r1", "status": "HEALTHY", "message": "ping", "checked_at": "2026-09-21T00:00:00+00:00"},
        "mq:m1": {"name": "m1", "status": "CRITICAL", "message": "down", "checked_at": "2026-09-21T00:00:00+00:00"},
        "robot:b1": {"name": "b1", "status": "UNKNOWN", "message": "no data", "checked_at": "2026-09-21T00:00:00+00:00"},
    })
    r = await client.get("/api/sites/sz/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["overall"] == "CRITICAL"  # worst wins
    assert body["summary"]["server"] == {"total": 2, "healthy": 1, "warning": 1, "critical": 0, "unknown": 0}
    assert body["summary"]["robot"]["unknown"] == 1
    issue_kinds = [(i["kind"], i["status"]) for i in body["issues"]]
    assert ("mq", "CRITICAL") in issue_kinds and ("server", "WARNING") in issue_kinds
    assert isinstance(body["recent_ops"], list)  # 建站本身已产生 SITE_CREATED 日志


async def test_overview_recent_ops(client, fake_platform_redis):
    from backend.app.core import oplog

    await oplog.record("sz", "redis/r1", "REDIS_DELETE_KEY", target="k1")
    body = (await client.get("/api/sites/sz/overview")).json()
    assert body["recent_ops"][0]["operation"] == "REDIS_DELETE_KEY"


async def test_overview_empty_site_healthy(client, fake_platform_redis):
    body = (await client.get("/api/sites/sz/overview")).json()
    assert body["overall"] == "HEALTHY"  # 无资源无检查 -> HEALTHY（非 UNKNOWN）
    assert all(v["total"] == 0 for v in body["summary"].values())


async def test_overview_unknown_site_404(client):
    assert (await client.get("/api/sites/nope/overview")).status_code == 404


async def test_check_site_isolates_failures(client, fake_platform_redis, monkeypatch):
    """单资源检查失败（CRITICAL）不影响其他资源（验收 7）。"""
    from backend.app.modules.redis.provider import TargetRedisProvider
    from backend.app.modules.server.provider import SSHServerMetricsProvider

    async def boom(self):
        raise RuntimeError("ssh down")

    async def ok_info(self, db=None):
        return {"status": "ok", "version": "7.2.4", "memory_used": 123}

    monkeypatch.setattr(SSHServerMetricsProvider, "health_check", boom)
    monkeypatch.setattr(TargetRedisProvider, "get_info", ok_info)
    await client.post("/api/sites/sz/servers", json={"id": "s1", "name": "s1", "host": "h", "username": "u", "password": "p"})
    await client.post("/api/sites/sz/redis", json={"id": "r1", "name": "r1", "host": "h"})

    count = await service.check_site("sz")
    assert count == 2
    raw = await fake_platform_redis.hgetall("ops:health:sz")
    server = json.loads(raw["server:s1"])
    redis = json.loads(raw["redis:r1"])
    assert server["status"] == "CRITICAL" and "ssh down" in server["message"]
    assert redis["status"] == "HEALTHY"
