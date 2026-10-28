import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core.redis import get_platform_redis
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

    # 创建：接口永不回明文（2026-10-22 用户决策：F12/抓包不可见）——password 换 has_password
    r = await client.post(
        "/api/sites/sz-test/redis",
        json={"id": "redis-01", "name": "redis-01", "host": "10.10.1.20", "password": "secret"},
    )
    assert r.status_code == 201
    body = r.json()
    assert "password" not in body and body["has_password"] is True

    # 存储层仍为明文（后端 provider 建连依赖，不经任何 API 响应）
    raw = await fake_platform_redis.hget(resource_key("sz-test", "redis"), "redis-01")
    assert json.loads(raw)["password"] == "secret"

    # 列表 / 详情均脱敏
    r = await client.get("/api/sites/sz-test/redis")
    assert "password" not in r.json()[0] and r.json()[0]["has_password"] is True
    r = await client.get("/api/sites/sz-test/redis/redis-01")
    assert "password" not in r.json() and r.json()["has_password"] is True

    # 更新：显式提交新密码 = 覆盖
    r = await client.put(
        "/api/sites/sz-test/redis/redis-01", json={"name": "redis-01改", "password": "newpass"}
    )
    raw = await fake_platform_redis.hget(resource_key("sz-test", "redis"), "redis-01")
    stored = json.loads(raw)
    assert stored["password"] == "newpass"
    assert stored["name"] == "redis-01改"

    # 更新不带 password 字段 = 保留原值（编辑表单密码留空即保持）
    r = await client.put("/api/sites/sz-test/redis/redis-01", json={"name": "x2"})
    raw = await fake_platform_redis.hget(resource_key("sz-test", "redis"), "redis-01")
    assert json.loads(raw)["password"] == "newpass"

    # 删除
    assert (await client.delete("/api/sites/sz-test/redis/redis-01")).status_code == 204
    assert (await client.get("/api/sites/sz-test/redis/redis-01")).status_code == 404

    # oplog：target/resource 用资源名（删除前最后改名为 x2），内部 id 进 params
    from backend.app.core import oplog

    entry = (await oplog.read_recent(1))[0]
    assert entry["operation"] == "RESOURCE_CONFIG_DELETED"
    assert entry["target"] == "x2"
    assert entry["resource"] == "redis/x2"
    assert entry["params"]["resource_id"] == "redis-01"


async def test_server_resource_defaults(client, fake_platform_redis):
    await _make_site(client)
    r = await client.post(
        "/api/sites/sz-test/servers", json={"id": "srv-01", "name": "srv-01", "host": "10.10.1.10", "username": "u", "password": "p"}
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


async def test_page_resource_url_or_html_and_kind(client):
    """pages 资源：url 与 html 二选一；kind 读取时派生（url 优先）。"""
    await _make_site(client)

    r = await client.post("/api/sites/sz-test/pages", json={
        "id": "p-url", "name": "Grafana", "url": "https://grafana.example.com"})
    assert r.status_code == 201
    assert r.json()["kind"] == "url"

    r = await client.post("/api/sites/sz-test/pages", json={
        "id": "p-html", "name": "旧页", "html": "<!doctype html><html><body>x</body></html>"})
    assert r.status_code == 201
    assert r.json()["kind"] == "html"

    # 二者皆空 → 422
    r = await client.post("/api/sites/sz-test/pages", json={"id": "p-empty", "name": "空"})
    assert r.status_code == 422

    # PUT 编辑路径同样受 validator 约束（_update_model metadata 修复的回归断言）
    r = await client.put("/api/sites/sz-test/pages/p-url", json={"url": "ftp://bad"})
    assert r.status_code == 422

    # kind 不落存储
    raw = await get_platform_redis().hget(resource_key("sz-test", "pages"), "p-html")
    assert "kind" not in json.loads(raw)
    listed = (await client.get("/api/sites/sz-test/pages")).json()
    assert {p["id"]: p["kind"] for p in listed} == {"p-url": "url", "p-html": "html"}


async def test_resource_name_must_be_unique_per_type(client):
    """同站点同类型下 name 唯一：create 重名 409；update 改成他者之名 409。"""
    await _make_site(client)

    # 同 type 下重名创建 → 409
    r = await client.post("/api/sites/sz-test/servers", json={
        "id": "s1", "name": "SAME", "host": "10.0.0.1", "username": "u", "password": "p"})
    assert r.status_code == 201
    r = await client.post("/api/sites/sz-test/servers", json={
        "id": "s2", "name": "SAME", "host": "10.0.0.2", "username": "u", "password": "p"})
    assert r.status_code == 409  # 重名被拒（s2 未创建）

    # 另建一个不同名资源，之后把它改名成已占用之名 → 409
    r = await client.post("/api/sites/sz-test/servers", json={
        "id": "s3", "name": "ALPHA", "host": "10.0.0.3", "username": "u", "password": "p"})
    assert r.status_code == 201
    r = await client.put("/api/sites/sz-test/servers/s3", json={"name": "SAME"})
    assert r.status_code == 409

    # 未改名（保存自身原名）应放行
    r = await client.put("/api/sites/sz-test/servers/s3", json={"name": "ALPHA"})
    assert r.status_code == 200

    # 不同类型不互斥：pages 可叫 SAME
    r = await client.post("/api/sites/sz-test/pages", json={
        "id": "pg", "name": "SAME", "description": "", "url": "https://x.example"})
    assert r.status_code == 201
