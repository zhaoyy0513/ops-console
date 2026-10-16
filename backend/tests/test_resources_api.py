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

    # 创建：明文回显（内部工具全明文，2026-09-22 用户决策）
    r = await client.post(
        "/api/sites/sz-test/redis",
        json={"id": "redis-01", "name": "redis-01", "host": "10.10.1.20", "password": "secret"},
    )
    assert r.status_code == 201
    assert r.json()["password"] == "secret"

    # 存储层一致
    raw = await fake_platform_redis.hget(resource_key("sz-test", "redis"), "redis-01")
    assert json.loads(raw)["password"] == "secret"

    # 列表 / 详情均明文
    r = await client.get("/api/sites/sz-test/redis")
    assert r.json()[0]["password"] == "secret"
    r = await client.get("/api/sites/sz-test/redis/redis-01")
    assert r.json()["password"] == "secret"

    # 更新：提交什么存什么（编辑表单预填原密码，改动即覆盖）
    r = await client.put(
        "/api/sites/sz-test/redis/redis-01", json={"name": "redis-01改", "password": "newpass"}
    )
    raw = await fake_platform_redis.hget(resource_key("sz-test", "redis"), "redis-01")
    stored = json.loads(raw)
    assert stored["password"] == "newpass"
    assert stored["name"] == "redis-01改"

    # 更新不带 password 字段 = 保留原值（exclude_unset 语义）
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

    # url 型
    r = await client.post("/api/sites/sz-test/pages", json={
        "id": "p-url", "name": "Grafana", "description": "监控大盘",
        "url": "https://10.102.129.12:3000",
    })
    assert r.status_code == 201
    assert r.json()["kind"] == "url"

    # html 型（单文件内联）
    r = await client.post("/api/sites/sz-test/pages", json={
        "id": "p-html", "name": "说明页", "description": "内嵌页面",
        "html": "<!doctype html><html><body><h1>Ops Runbook</h1></body></html>",
    })
    assert r.status_code == 201
    assert r.json()["kind"] == "html"

    # 两者都无 -> 422（pydantic model_validator）
    r = await client.post("/api/sites/sz-test/pages", json={
        "id": "p-none", "name": "空", "description": "无内容",
    })
    assert r.status_code == 422

    # url 非法（非 http/https）-> 422
    r = await client.post("/api/sites/sz-test/pages", json={
        "id": "p-bad", "name": "坏链", "description": "x", "url": "ftp://x",
    })
    assert r.status_code == 422

    # 列表顺序固定 url 优先（两个都有时）
    r = await client.put("/api/sites/sz-test/pages/p-html", json={
        "url": "http://example.com", "html": None,
    })
    assert r.status_code == 200
    assert r.json()["kind"] == "url"  # url 优先于 html

    # kind 不落存储：存储层无 kind 键，读取时重新派生
    from backend.app.core.redis import get_platform_redis
    from backend.app.modules.sites.service import resource_key

    raw = await get_platform_redis().hget(resource_key("sz-test", "pages"), "p-html")
    assert "kind" not in json.loads(raw)
    listed = (await client.get("/api/sites/sz-test/pages")).json()
    assert {p["id"]: p["kind"] for p in listed} == {"p-url": "url", "p-html": "url"}
