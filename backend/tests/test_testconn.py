import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.shared import testconn
from backend.app.shared.errors import OpsError


@pytest.fixture
async def client(fake_platform_redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_unknown_type_returns_envelope(client):
    r = await client.post(
        "/api/test-connection", json={"type": "no-such", "config": {}}
    )
    assert r.status_code == 400
    body = r.json()
    assert body["success"] is False
    assert body["error_code"] == "UNKNOWN_RESOURCE_TYPE"


async def test_registered_tester_success(client, monkeypatch):
    async def fake_tester(config: dict) -> dict:
        return {"success": True, "latency_ms": 12, "message": "Connected, Redis 7.2.4"}

    monkeypatch.setitem(testconn._testers, "redis", fake_tester)
    r = await client.post(
        "/api/test-connection", json={"type": "redis", "config": {"host": "h"}}
    )
    assert r.status_code == 200
    assert r.json() == {"success": True, "latency_ms": 12, "message": "Connected, Redis 7.2.4"}


async def test_tester_ops_error_becomes_failure_body(client, monkeypatch):
    async def failing_tester(config: dict) -> dict:
        raise OpsError("REMOTE_CONNECTION_FAILED", "Connection timed out after 3s")

    monkeypatch.setitem(testconn._testers, "server", failing_tester)
    r = await client.post(
        "/api/test-connection", json={"type": "server", "config": {"host": "h"}}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["message"] == "Connection timed out after 3s"
