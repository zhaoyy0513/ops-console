import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest.fixture
async def client(fake_platform_redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_site_crud_and_enable(client):
    r = await client.post("/api/sites", json={"id": "sz-test", "name": "深圳测试站"})
    assert r.status_code == 201
    assert r.json()["id"] == "sz-test"
    assert r.json()["enabled"] is True

    r = await client.get("/api/sites")
    assert [s["id"] for s in r.json()] == ["sz-test"]

    r = await client.get("/api/sites/sz-test")
    assert r.json()["name"] == "深圳测试站"

    r = await client.put("/api/sites/sz-test", json={"name": "深圳测试站-改", "enabled": False})
    assert r.json()["enabled"] is False
    assert r.json()["name"] == "深圳测试站-改"

    r = await client.delete("/api/sites/sz-test")
    assert r.status_code == 204
    assert (await client.get("/api/sites/sz-test")).status_code == 404


async def test_create_duplicate_site_conflict(client):
    await client.post("/api/sites", json={"id": "a", "name": "A"})
    r = await client.post("/api/sites", json={"id": "a", "name": "A2"})
    assert r.status_code == 409


async def test_create_site_auto_id(client):
    r = await client.post("/api/sites", json={"name": "无ID站点"})
    assert r.status_code == 201
    assert r.json()["id"]
