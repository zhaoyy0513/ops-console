import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.modules.server import service as server_service
from backend.app.shared.errors import OpsError


@pytest.fixture
async def client(fake_platform_redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _seed(client):
    await client.post("/api/sites", json={"id": "sz-test", "name": "深圳测试站"})
    r = await client.post(
        "/api/sites/sz-test/servers",
        json={"id": "srv-01", "name": "srv", "host": "1.2.3.4"},
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
