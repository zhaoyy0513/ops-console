import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.modules.overview import service
from backend.app.modules.overview.service import hygiene_issues


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
        "device:b1": {"name": "b1", "status": "UNKNOWN", "message": "no data", "checked_at": "2026-09-21T00:00:00+00:00"},
    })
    r = await client.get("/api/sites/sz/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["overall"] == "CRITICAL"  # worst wins
    assert body["summary"]["server"] == {"total": 2, "healthy": 1, "warning": 1, "critical": 0, "unknown": 0}
    assert body["summary"]["device"]["unknown"] == 1
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

    async def ok_test(self, db=None):
        return "Connected, Redis 7.2.4"

    monkeypatch.setattr(SSHServerMetricsProvider, "health_check", boom)
    monkeypatch.setattr(TargetRedisProvider, "run_test", ok_test)
    await client.post("/api/sites/sz/servers", json={"id": "s1", "name": "s1", "host": "h", "username": "u", "password": "p"})
    await client.post("/api/sites/sz/redis", json={"id": "r1", "name": "r1", "host": "h"})

    count = await service.check_site("sz")
    assert count == 2
    raw = await fake_platform_redis.hgetall("ops:health:sz")
    server = json.loads(raw["server:s1"])
    redis = json.loads(raw["redis:r1"])
    assert server["status"] == "CRITICAL" and "ssh down" in server["message"]
    assert redis["status"] == "HEALTHY"


# ---------- 配置卫生清单（纯静态判定） ----------


def test_hygiene_flags_each_check():
    site = {"thresholds": None}
    resources = {
        "servers": [{"id": "s1", "name": "s1"}],
        "devices": [{"id": "d1", "name": "d1"}],
        "redis": [{"id": "r1", "name": "r1", "password": ""}],
        "mq": [{"id": "m1", "name": "m1"}],
        "pages": [{"id": "p1", "name": "p1", "url": "", "html": ""}],
    }
    got = {(i["type"], i["severity"], i["resource_name"]) for i in hygiene_issues(site, resources)}
    assert got == {
        ("server_no_thresholds", "info", "s1"),
        ("device_no_field_map", "info", "d1"),
        ("redis_no_password", "warning", "r1"),
        ("mq_no_password", "warning", "m1"),
        ("page_empty", "warning", "p1"),
    }
    assert hygiene_issues(site, resources)[0]["severity"] == "warning"  # 警告在前


def test_hygiene_clean_config_and_disabled_skipped():
    site = {"thresholds": {"cpu_warning": 80}}
    resources = {
        "servers": [{"id": "s1", "name": "s1"}],
        "devices": [{"id": "d1", "name": "d1", "custom_fields": [{"key": "cf_1"}]}],
        # 停用资源不参与卫生检查
        "redis": [{"id": "r1", "name": "r1", "password": "p"},
                  {"id": "r2", "name": "r2", "password": "", "enabled": False}],
        "mq": [{"id": "m1", "name": "m1", "password": "p"}],
        "pages": [{"id": "p1", "name": "p1", "url": "http://x"}],
    }
    assert hygiene_issues(site, resources) == []


async def test_hygiene_api(client):
    await client.post("/api/sites/sz/redis", json={"id": "r1", "name": "r1", "host": "h"})
    r = await client.get("/api/overview/sz/hygiene")
    assert r.status_code == 200
    body = r.json()
    assert any(i["type"] == "redis_no_password" and i["resource_name"] == "r1" for i in body)
    assert (await client.get("/api/overview/nope/hygiene")).status_code == 404


# ---------- 事件时间轴 ----------


async def test_events_order_and_limit(fake_platform_redis):
    from backend.app.core import events

    for i in range(3):
        await events.record_event("sz", "diag", f"e{i}", detail=str(i))
    out = await events.read_events("sz", 2)
    assert [e["title"] for e in out] == ["e2", "e1"]
    assert out[0]["kind"] == "diag" and out[0]["detail"] == "2"

    for i in range(205):
        await events.record_event("sz", "config", f"x{i}")
    assert len(await events.read_events("sz", 500)) == 200  # 上限 200
    assert (await events.read_events("sz", 1))[0]["title"] == "x204"


async def test_event_write_failure_is_swallowed(monkeypatch):
    from backend.app.core import events

    class Boom:
        def pipeline(self, transaction=True):
            raise RuntimeError("redis down")

    monkeypatch.setattr(events, "get_platform_redis", lambda: Boom())
    await events.record_event("sz", "diag", "must not raise")


async def test_check_site_records_status_transitions(client, fake_platform_redis, monkeypatch):
    """非 CRITICAL→CRITICAL 记一条，持续 CRITICAL 不重复，恢复再记一条。"""
    from backend.app.core import events
    from backend.app.modules.redis.provider import TargetRedisProvider

    state = {"fail": False}

    async def run_test(self, db=None):
        if state["fail"]:
            raise RuntimeError("redis down")
        return "Connected"

    monkeypatch.setattr(TargetRedisProvider, "run_test", run_test)
    await client.post("/api/sites/sz/redis", json={"id": "r1", "name": "r1", "host": "h"})

    await service.check_site("sz")  # 首检 HEALTHY：无旧值，不记
    assert await events.read_events("sz") == []

    state["fail"] = True
    await service.check_site("sz")
    ev = await events.read_events("sz")
    assert len(ev) == 1 and ev[0]["kind"] == "diag" and "CRITICAL" in ev[0]["title"]

    await service.check_site("sz")  # 仍 CRITICAL：不重复
    assert len(await events.read_events("sz")) == 1

    state["fail"] = False
    await service.check_site("sz")  # 恢复
    ev = await events.read_events("sz")
    assert len(ev) == 2 and "→ HEALTHY" in ev[0]["title"]

    api_ev = (await client.get("/api/overview/sz/events?limit=10")).json()
    assert len(api_ev) == 2
