import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core import oplog
from backend.app.main import app


@pytest.fixture
async def client(fake_platform_redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _seed(client):
    await client.post("/api/sites", json={"id": "sz-test", "name": "深圳测试站"})
    await client.post(
        "/api/sites/sz-test/redis",
        json={"id": "redis-01", "name": "redis-01", "host": "10.10.1.20", "password": "secret"},
    )
    await client.post(
        "/api/sites/sz-test/servers", json={"id": "srv-01", "name": "srv-01", "host": "10.10.1.10"}
    )


async def test_export_contains_passwords(client, fake_platform_redis):
    await _seed(client)
    r = await client.post("/api/sites/export")
    assert r.status_code == 200
    site = r.json()["sites"][0]
    assert site["id"] == "sz-test"
    assert site["redis"][0]["password"] == "secret"  # 导出含密码
    assert site["servers"][0]["host"] == "10.10.1.10"
    assert "password" not in site or site.get("password") is None


async def test_export_import_roundtrip(client, fake_platform_redis):
    await _seed(client)
    exported = (await client.post("/api/sites/export")).json()

    # 清空（验收：export → 清 → import 一致）
    await client.delete("/api/sites/sz-test")
    assert (await client.get("/api/sites")).json() == []

    r = await client.post("/api/sites/import", json=exported)
    assert r.status_code == 200
    assert r.json()["imported"] == 1

    # 站点与资源一致
    site = (await client.get("/api/sites/sz-test")).json()
    assert site["name"] == "深圳测试站"
    redis_items = (await client.get("/api/sites/sz-test/redis")).json()
    assert redis_items[0]["id"] == "redis-01"
    assert redis_items[0]["host"] == "10.10.1.20"

    # 导入记录操作日志（验收 13）
    entries = await oplog.read_recent(3)
    assert any(e["operation"] == "IMPORT_CONFIG" for e in entries)


async def test_import_malformed_payload_422(client):
    r = await client.post("/api/sites/import", json={"no_sites": True})
    assert r.status_code == 422
