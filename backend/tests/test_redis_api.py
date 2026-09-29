import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from backend.app.core import oplog
from backend.app.main import app
from backend.app.modules.redis.provider import TargetRedisProvider


@pytest.fixture
async def target_redis(fake_platform_redis):
    """被监控 Redis 的替身：patch provider 连接工厂，与平台 fakeredis 独立实例。"""
    r = FakeRedis(decode_responses=True)
    original = TargetRedisProvider._client

    def fake_client(self, db=None):
        return r

    TargetRedisProvider._client = fake_client  # type: ignore[method-assign]
    yield r
    TargetRedisProvider._client = original  # type: ignore[method-assign]


CANNED_INFO = {
    "redis_version": "7.2.4",
    "uptime_in_seconds": 86400,
    "used_memory": 1_000_000,
    "used_memory_peak": 2_000_000,
    "mem_fragmentation_ratio": 1.2,
    "connected_clients": 5,
    "total_commands_processed": 1000,
    "keyspace_hits": 700,
    "keyspace_misses": 300,
    "evicted_keys": 2,
    "expired_keys": 10,
    "db_size": 42,
}


class _StubInfoClient:
    """fakeredis 无 INFO 命令，info/tester 路径用此 stub。"""

    def __init__(self, provider, db=None):
        pass

    async def info(self, section=None):
        return CANNED_INFO

    async def dbsize(self):
        return CANNED_INFO["db_size"]

    async def ping(self):
        return True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def close(self):
        pass

    async def wait_closed(self):
        return None


@pytest.fixture
def patch_info_client(monkeypatch):
    monkeypatch.setattr(TargetRedisProvider, "_client", lambda self, db=None: _StubInfoClient(self, db))


@pytest.fixture
async def client(fake_platform_redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
async def seeded(client):
    assert (await client.post("/api/sites", json={"id": "sz", "name": "S"})).status_code == 201
    r = await client.post(
        "/api/sites/sz/redis",
        json={"id": "r1", "name": "r1", "host": "target", "port": 6379, "password": "pw"},
    )
    assert r.status_code == 201


# ---------- T16: info + tester ----------


async def test_normalize_info_pure():
    from backend.app.modules.redis.provider import normalize_info

    body = normalize_info(CANNED_INFO)
    assert body["version"] == "7.2.4"
    assert body["memory_used"] == 1_000_000
    assert body["hit_rate"] == 70.0
    assert body["db_size"] == 42
    # 空数据不炸
    empty = normalize_info({})
    assert empty["hit_rate"] is None and empty["version"] is None


async def test_info_endpoint(client, patch_info_client):
    r = await client.get("/api/sites/sz/redis/r1/info")
    assert r.status_code == 200
    body = r.json()
    for field in ("status", "version", "memory_used", "memory_peak", "memory_fragmentation",
                  "connected_clients", "hit_rate", "evicted_keys", "expired_keys", "db_size"):
        assert field in body, f"missing {field}"
    assert body["version"] == "7.2.4"


async def test_redis_tester_via_test_connection(client, patch_info_client):
    r = await client.post("/api/test-connection", json={"type": "redis", "config": {"host": "target"}})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["message"] == "Connected, Redis 7.2.4"


# ---------- T17: SCAN 浏览 + Key 详情 ----------


async def _seed_keys(target_redis):
    await target_redis.set("robot:001", "a")
    await target_redis.set("robot:002", "b")
    await target_redis.hset("user:1", mapping={"name": "n"})
    await target_redis.sadd("tags", "x", "y")
    await target_redis.rpush("queue", "j1", "j2")
    await target_redis.zadd("rank", {"m1": 1.5, "m2": 2.5})


async def test_scan_pagination_and_type_filter(client, target_redis):
    await _seed_keys(target_redis)
    # pattern 过滤（显式 glob 走 SCAN MATCH 原语义）
    r = await client.get("/api/sites/sz/redis/r1/keys", params={"pattern": "robot:*", "count": 10})
    body = r.json()
    assert {k["key"] for k in body["keys"]} == {"robot:001", "robot:002"}
    # type 过滤
    r = await client.get("/api/sites/sz/redis/r1/keys", params={"type": "hash"})
    assert [k["key"] for k in r.json()["keys"]] == ["user:1"]
    # 非法 type 400
    r = await client.get("/api/sites/sz/redis/r1/keys", params={"type": "bogus"})
    assert r.status_code == 400


async def test_fuzzy_case_insensitive_search(client, target_redis):
    """模糊子串 + 忽略大小写（用户需求）：小写搜大写、大写搜小写、子串命中。"""
    await target_redis.set("COMPLETE_TPS_INFO:6", "a")
    await target_redis.set("COMPLETE_TPS_INFO:7", "b")
    await target_redis.set("robot:001", "c")

    # 小写子串命中大写 key
    r = await client.get("/api/sites/sz/redis/r1/keys", params={"pattern": "tps_info", "count": 10})
    assert {k["key"] for k in r.json()["keys"]} == {"COMPLETE_TPS_INFO:6", "COMPLETE_TPS_INFO:7"}
    # 大写子串命中小写 key
    r = await client.get("/api/sites/sz/redis/r1/keys", params={"pattern": "ROBOT:", "count": 10})
    assert {k["key"] for k in r.json()["keys"]} == {"robot:001"}
    # count 截断 + cursor 翻页语义（非 0 cursor 表示还有更多）
    r = await client.get("/api/sites/sz/redis/r1/keys", params={"pattern": "tps", "count": 1})
    body = r.json()
    assert body["count"] == 1


async def test_key_detail_all_types(client, target_redis):
    await _seed_keys(target_redis)
    r = await client.get("/api/sites/sz/redis/r1/key", params={"key": "robot:001"})
    body = r.json()
    assert body["type"] == "string" and body["value"] == "a"
    assert body["ttl"] == -1  # 无过期

    body = (await client.get("/api/sites/sz/redis/r1/key", params={"key": "user:1"})).json()
    assert body["type"] == "hash" and body["value"] == {"name": "n"}

    body = (await client.get("/api/sites/sz/redis/r1/key", params={"key": "queue"})).json()
    assert body["value"] == ["j1", "j2"]

    body = (await client.get("/api/sites/sz/redis/r1/key", params={"key": "tags"})).json()
    assert body["value"] == ["x", "y"]

    body = (await client.get("/api/sites/sz/redis/r1/key", params={"key": "rank"})).json()
    assert body["value"] == [[1.5, "m1"], [2.5, "m2"]]

    # 不存在的 key 404
    r = await client.get("/api/sites/sz/redis/r1/key", params={"key": "nope"})
    assert r.status_code == 404


# ---------- T18: 操作 + 危险命令拒绝 + oplog ----------


async def test_set_string_and_expire_and_oplog(client, target_redis):
    r = await client.post(
        "/api/sites/sz/redis/r1/operations",
        json={"op": "set", "key": "nk", "type": "string", "value": "hello"},
    )
    assert r.status_code == 200
    assert await target_redis.get("nk") == "hello"

    r = await client.post(
        "/api/sites/sz/redis/r1/operations",
        json={"op": "expire", "key": "nk", "ttl": 120},
    )
    assert r.status_code == 200
    assert await target_redis.ttl("nk") > 0

    r = await client.post(
        "/api/sites/sz/redis/r1/operations",
        json={"op": "expire", "key": "nk", "ttl": -1},
    )
    assert r.status_code == 200
    assert await target_redis.ttl("nk") == -1

    entries = await oplog.read_recent(5)
    ops = [e["operation"] for e in entries]
    assert "REDIS_SET_KEY" in ops and "REDIS_EXPIRE_KEY" in ops
    # params 不含 value（PRD §17：记参数摘要即可，value 可能大/敏感）
    set_entry = next(e for e in entries if e["operation"] == "REDIS_SET_KEY")
    assert "value" not in (set_entry["params"] or {})


async def test_set_typed_values(client, target_redis):
    cases = [
        ({"type": "hash", "value": {"a": "1"}}, lambda: target_redis.hgetall("tk")),
        ({"type": "list", "value": ["l1", "l2"]}, lambda: target_redis.lrange("tk", 0, -1)),
        ({"type": "set", "value": ["s1", "s2"]}, lambda: target_redis.smembers("tk")),
        ({"type": "zset", "value": [[1.5, "m1"]]}, lambda: target_redis.zrange("tk", 0, -1, withscores=True)),
    ]
    for payload, reader in cases:
        r = await client.post("/api/sites/sz/redis/r1/operations", json={"op": "set", "key": "tk", **payload})
        assert r.status_code == 200
        assert await reader()


async def test_delete_and_oplog(client, target_redis):
    await target_redis.set("dk", "v")
    r = await client.post("/api/sites/sz/redis/r1/operations", json={"op": "delete", "key": "dk"})
    assert r.status_code == 200
    assert await target_redis.exists("dk") == 0
    entries = await oplog.read_recent(1)
    assert entries[0]["operation"] == "REDIS_DELETE_KEY"
    assert entries[0]["target"] == "dk"
    # resource 用实例名（seeded name=r1）而非内部 id；db/instance_id 进 params
    assert entries[0]["resource"] == "redis/r1"
    assert entries[0]["params"]["db"] == 0
    assert entries[0]["params"]["instance_id"] == "r1"


async def test_invalid_value_structure_rejected_before_redis(client, target_redis):
    """value 结构错误必须在校验层拦下，不触达 Redis。"""
    r = await client.post(
        "/api/sites/sz/redis/r1/operations",
        json={"op": "set", "key": "bk", "type": "hash", "value": "not-a-dict"},
    )
    assert r.status_code == 400
    assert await target_redis.exists("bk") == 0

    # op 白名单之外 → pydantic 枚举直接 422（实现层不可达）
    r = await client.post("/api/sites/sz/redis/r1/operations", json={"op": "flushall"})
    assert r.status_code == 422

    r = await client.post(
        "/api/sites/sz/redis/r1/operations", json={"op": "expire", "key": "x"}
    )
    assert r.status_code == 400  # 缺 ttl
