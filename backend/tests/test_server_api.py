import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.modules.server import service as server_service
from backend.app.shared.errors import OpsError

from backend.app.modules.server.provider import parse_diskstats


def test_parse_diskstats_excludes_partitions_and_loop():
    """分区（sda1 / nvme0n1p1）与 loop 不计入，避免与整盘双重计数。"""
    sample = (
        "   8       0 sda 100 0 2000 5 200 0 4000 8 0 10 10\n"
        "   8       1 sda1 50 0 1000 2 100 0 2000 4 0 5 5\n"
        "   7       0 loop0 5 0 10 1 0 0 0 0 0 1 1\n"
        " 259       0 nvme0n1 300 0 6000 9 400 0 8000 12 0 20 20\n"
        " 259       1 nvme0n1p1 50 0 1000 2 100 0 2000 4 0 5 5\n"
    )
    assert parse_diskstats(sample) == {
        "read_bytes": (2000 + 6000) * 512,
        "write_bytes": (4000 + 8000) * 512,
        "read_iops": 100 + 300,
        "write_iops": 200 + 400,
    }


def test_parse_diskstats_counts_dm_device_when_it_is_the_only_disk():
    """容器/device-mapper 场景：设备名不在 sda/nvme 白名单时也要采集（否则整卡永远 ?）。"""
    sample = " 253       0 dm-0 10 0 2000 5 20 0 4000 8 0 10 10 0 0 0 0\n"
    assert parse_diskstats(sample) == {
        "read_bytes": 2000 * 512,
        "write_bytes": 4000 * 512,
        "read_iops": 10,
        "write_iops": 20,
    }


def test_parse_diskstats_empty_returns_none():
    """完全无可用设备 → None（前端显示 ?，不误报 0）。"""
    assert parse_diskstats("") is None
    assert parse_diskstats("   7       0 loop0 5 0 10 1 0 0 0 0 0 1 1\n") is None


@pytest.fixture
async def client(fake_platform_redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _seed(client):
    await client.post("/api/sites", json={"id": "sz-test", "name": "深圳测试站"})
    r = await client.post(
        "/api/sites/sz-test/servers",
        json={"id": "srv-01", "name": "srv", "host": "1.2.3.4", "username": "u", "password": "p"},
    )
    assert r.status_code == 201


class FakeProvider:
    calls = 0

    def __init__(self, config: dict):
        pass

    async def get_metrics(self):
        type(self).calls += 1
        await asyncio.sleep(0.05)
        return {"cpu": {"usage": 50.0}}

    async def get_processes(self):
        type(self).calls += 1
        await asyncio.sleep(0.05)
        return [{"pid": 1}]

    async def run_test(self):
        type(self).calls += 1
        await asyncio.sleep(0.01)
        return "SSH OK, 4 cores"


@pytest.fixture
def fake_provider(monkeypatch):
    FakeProvider.calls = 0
    monkeypatch.setattr(server_service, "_build_provider", lambda config: FakeProvider(config))
    return FakeProvider


async def test_concurrent_requests_single_ssh(client, fake_provider):
    """PRD §15：并发 10 次同一 server 查询只产生 1 次 SSH。"""
    await _seed(client)

    async def one():
        return await client.get("/api/sites/sz-test/servers/srv-01/metrics")

    responses = await asyncio.gather(*(one() for _ in range(10)))
    assert all(r.status_code == 200 for r in responses)
    assert fake_provider.calls == 1


async def test_metrics_and_processes_cached_separately(client, fake_provider):
    await _seed(client)
    await client.get("/api/sites/sz-test/servers/srv-01/metrics")
    await client.get("/api/sites/sz-test/servers/srv-01/metrics")
    assert fake_provider.calls == 1
    await client.get("/api/sites/sz-test/servers/srv-01/processes")
    assert fake_provider.calls == 2


async def test_ssh_failure_returns_envelope(client, fake_provider, monkeypatch):
    """验收 7：查询失败不 500，统一错误包络。"""
    await _seed(client)

    async def boom(self):
        raise OpsError("REMOTE_CONNECTION_FAILED", "Unable to connect to server", "srv-01")

    monkeypatch.setattr(fake_provider, "get_metrics", boom)
    r = await client.get("/api/sites/sz-test/servers/srv-01/metrics")
    assert r.status_code == 502
    body = r.json()
    assert body["success"] is False
    assert body["error_code"] == "REMOTE_CONNECTION_FAILED"
    assert body["resource"] == "srv-01"


async def test_unknown_server_404(client, fake_provider):
    r = await client.get("/api/sites/sz-test/servers/nope/metrics")
    assert r.status_code == 404


async def test_server_connection_tester(client, fake_provider):
    await _seed(client)
    r = await client.post(
        "/api/test-connection",
        json={"type": "server", "config": {"host": "1.2.3.4", "username": "u"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "SSH OK" in body["message"]
