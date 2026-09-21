import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.modules.sites.service import resource_key


@pytest.fixture
async def client(fake_platform_redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _make_site(client):
    r = await client.post("/api/sites", json={"id": "sz-test", "name": "深圳测试站"})
    assert r.status_code == 201


async def test_redis_resource_crud_and_password_rules(client, fake_platform_redis):
    await _make_site(client)

    # 创建：带密码；响应不回显
    r = await client.post(
        "/api/sites/sz-test/redis",
        json={"id": "redis-01", "name": "redis-01", "host": "10.10.1.20", "password": "secret"},
    )
    assert r.status_code == 201
    assert r.json()["password"] == ""

    # 存储层确有密码
    raw = await fake_platform_redis.hget(resource_key("sz-test", "redis"), "redis-01")
    assert json.loads(raw)["password"] == "secret"

    # 列表 / 详情均不回显
    r = await client.get("/api/sites/sz-test/redis")
    assert r.json()[0]["password"] == ""
    r = await client.get("/api/sites/sz-test/redis/redis-01")
    assert r.json()["password"] == ""

    # 更新：密码留空 = 不修改
    r = await client.put(
        "/api/sites/sz-test/redis/redis-01", json={"name": "redis-01改", "password": ""}
    )
    assert r.status_code == 200
    raw = await fake_platform_redis.hget(resource_key("sz-test", "redis"), "redis-01")
    stored = json.loads(raw)
    assert stored["password"] == "secret"
    assert stored["name"] == "redis-01改"

    # 更新：提供新密码则覆盖
    r = await client.put(
        "/api/sites/sz-test/redis/redis-01", json={"password": "newpass"}
    )
    raw = await fake_platform_redis.hget(resource_key("sz-test", "redis"), "redis-01")
    assert json.loads(raw)["password"] == "newpass"

    # 删除
    assert (await client.delete("/api/sites/sz-test/redis/redis-01")).status_code == 204
    assert (await client.get("/api/sites/sz-test/redis/redis-01")).status_code == 404


async def test_server_resource_defaults(client, fake_platform_redis):
    await _make_site(client)
    r = await client.post(
        "/api/sites/sz-test/servers", json={"id": "srv-01", "name": "srv-01", "host": "10.10.1.10"}
    )
    assert r.status_code == 201
    assert r.json()["port"] == 22

    r = await client.get("/api/sites/sz-test/servers")
    assert [s["id"] for s in r.json()] == ["srv-01"]


async def test_resource_missing_required_field_422(client):
    await _make_site(client)
    r = await client.post("/api/sites/sz-test/redis", json={"id": "x", "name": "x"})
    assert r.status_code == 422


async def test_resource_on_missing_site_404(client):
    r = await client.get("/api/sites/no-such/redis")
    assert r.status_code == 404


async def test_delete_site_cascades_resources(client, fake_platform_redis):
    await _make_site(client)
    await client.post(
        "/api/sites/sz-test/redis", json={"id": "redis-01", "name": "r", "host": "h"}
    )
    r = await client.delete("/api/sites/sz-test")
    assert r.status_code == 204
    assert not await fake_platform_redis.hexists(resource_key("sz-test", "redis"), "redis-01")
