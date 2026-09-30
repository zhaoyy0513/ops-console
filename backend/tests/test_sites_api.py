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

    # oplog target 用站点名（而非内部 id）；site_id 进 params
    from backend.app.core import oplog

    entries = await oplog.read_recent(3)
    assert [e["operation"] for e in entries] == ["SITE_DELETED", "SITE_UPDATED", "SITE_CREATED"]
    assert all(e["target"] != "sz-test" for e in entries)
    assert entries[0]["target"] == "深圳测试站-改"
    assert entries[0]["params"]["site_id"] == "sz-test"


async def test_delete_site_purges_sample_keys(client, fake_platform_redis):
    """删站点必须连带清掉该站点的趋势采样 key（孤儿样本无读者、无 TTL 兜底路径之外的清理）。"""
    from backend.app.core import sampling

    await client.post("/api/sites", json={"id": "s1", "name": "S1"})
    await sampling.push_sample("server:s1:srv1", "cpu", 1.2)
    await sampling.push_sample("mq:s1:mq1:abc123def4", "backlog", 5)
    assert await fake_platform_redis.exists("ops:sample:server:s1:srv1:cpu")
    assert await fake_platform_redis.exists("ops:sample:mq:s1:mq1:abc123def4:backlog")

    r = await client.delete("/api/sites/s1")
    assert r.status_code == 204
    assert not await fake_platform_redis.exists("ops:sample:server:s1:srv1:cpu")
    assert not await fake_platform_redis.exists("ops:sample:mq:s1:mq1:abc123def4:backlog")


async def test_create_duplicate_site_conflict(client):
    await client.post("/api/sites", json={"id": "a", "name": "A"})
    r = await client.post("/api/sites", json={"id": "a", "name": "A2"})
    assert r.status_code == 409


async def test_create_site_auto_id(client):
    r = await client.post("/api/sites", json={"name": "无ID站点"})
    assert r.status_code == 201
    assert r.json()["id"]
