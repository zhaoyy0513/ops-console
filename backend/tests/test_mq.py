import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core import sampling
from backend.app.main import app
from backend.app.modules.mq import provider, service


# ---------- 纯函数解析（现场抓取的 Jolokia 响应样本） ----------

BROKER_ATTRS = {
    "Name": "0.0.0.0",
    "Version": "2.44.0",
    "Uptime": "5 days 2 hours",
    "ConnectionCount": 23,
    "TotalConnectionCount": 76559,
    "SessionCount": 38,
    "TotalConsumerCount": 11,
    "TotalProducerCount": None,
    "AddressCount": 98,
    "Status": '{"server":{"state":"STARTED","version":"2.44.0"}}',
}

QUEUE_VALUE = {
    'org.apache.activemq.artemis:address="a",broker="b",component=addresses,queue="q1",routing-type="multicast",subcomponent=queues': {
        "Name": "q1", "Address": "a", "RoutingType": "MULTICAST",
        "MessageCount": 12381, "ConsumerCount": 0, "DeliveringCount": 2,
        "MessagesAdded": 50000, "MessagesAcknowledged": 37600,
    },
    'org.apache.activemq.artemis:address="a",broker="b",component=addresses,queue="q2",routing-type="anycast",subcomponent=queues': {
        "Name": "q2", "Address": "a", "RoutingType": "ANYCAST",
        "MessageCount": 5, "ConsumerCount": 1, "DeliveringCount": 0,
        "MessagesAdded": 100, "MessagesAcknowledged": 95,
    },
    # address 本体（无 subcomponent=queues）应被过滤
    'org.apache.activemq.artemis:address="a",broker="b",component=addresses': {"Name": "a"},
}


def test_normalize_broker():
    b = provider.normalize_broker(BROKER_ATTRS)
    assert b["status"] == "STARTED"
    assert b["version"] == "2.44.0"
    assert b["connections"] == 23
    assert b["producers"] is None  # 2.44 无此属性 -> None
    # Status 非 JSON 时容错
    assert provider.normalize_broker({"Status": "weird"})["status"] == "weird"


def test_normalize_jvm():
    jvm = provider.normalize_jvm(
        {"HeapMemoryUsage": {"used": 125911096, "max": 2147483648}, "NonHeapMemoryUsage": {"used": 90000000}},
        {"ThreadCount": 117},
        {'java.lang:type=GarbageCollector,name="G1 Young Generation"': {"CollectionCount": 110, "CollectionTime": 2028},
         'java.lang:name="G1 Old Generation",type=GarbageCollector': {"CollectionCount": 3, "CollectionTime": 1500}},
    )
    assert jvm["heap_used"] == 125911096
    assert jvm["heap_max"] == 2147483648
    assert jvm["threads"] == 117
    assert [g["name"] for g in jvm["gc"]] == ["G1 Young Generation", "G1 Old Generation"]  # type= 段不入名


def test_normalize_queues_filters_and_sorts():
    queues = provider.normalize_queues(QUEUE_VALUE)
    assert [q["name"] for q in queues] == ["q1", "q2"]  # address 本体被滤掉，按 backlog 降序
    assert queues[0]["message_count"] == 12381


def test_parse_first_message_age():
    assert provider.parse_first_message_age(45000) == 45000
    assert provider.parse_first_message_age(0) == 0  # 0 是合法值（刚入队）
    assert provider.parse_first_message_age(1500.9) == 1500
    assert provider.parse_first_message_age(-1) is None  # 空队列 Artemis 给 -1
    assert provider.parse_first_message_age(None) is None  # 属性不存在
    assert provider.parse_first_message_age("123") is None  # 非数字
    assert provider.parse_first_message_age(True) is None


def test_normalize_queues_first_message_age():
    q1_key = next(k for k in QUEUE_VALUE if 'queue="q1"' in k)
    q2_key = next(k for k in QUEUE_VALUE if 'queue="q2"' in k)
    queues = provider.normalize_queues(QUEUE_VALUE, {
        q1_key: {"FirstMessageAge": 600000},
        q2_key: {"FirstMessageAge": -1},
    })
    assert queues[0]["first_message_age_ms"] == 600000
    assert queues[1]["first_message_age_ms"] is None
    # ages 缺失 / 属性读失败：整列为 None，其它字段完好
    no_age = provider.normalize_queues(QUEUE_VALUE)
    assert all(q["first_message_age_ms"] is None for q in no_age)
    assert no_age[0]["message_count"] == 12381


def test_diagnose_queue_rules():
    # backlog 超阈值
    d = service.diagnose_queue({"message_count": 12381, "consumer_count": 0, "growth_5m": None})
    assert d["status"] == "WARNING"
    assert {i["type"] for i in d["issues"]} == {"BACKLOG_HIGH", "NO_CONSUMER"}
    # critical
    assert service.diagnose_queue({"message_count": 20000, "consumer_count": 1, "growth_5m": None})["status"] == "CRITICAL"
    # 增长
    d = service.diagnose_queue({"message_count": 3000, "consumer_count": 1, "growth_5m": 10040})
    assert any(i["type"] == "BACKLOG_GROWING" for i in d["issues"])
    # 健康
    assert service.diagnose_queue({"message_count": 5, "consumer_count": 1, "growth_5m": 1})["status"] == "HEALTHY"
    # 空数据不炸
    assert service.diagnose_queue({})["status"] == "HEALTHY"


# ---------- 采样 ----------


async def test_sampling_push_and_read(fake_platform_redis):
    import time as _t

    await sampling.push_sample("mq1", "s1", 100)
    await sampling.push_sample("mq1", "s1", 200)  # 新值在前
    assert await sampling.value_minutes_ago("mq1", "s1", minutes=5) is None  # 无足够历史

    # 手写一条 6 分钟前的样本
    import json as _json

    r = fake_platform_redis
    old = _json.dumps({"ts": int(_t.time() - 360), "v": 50})
    await r.lpush(sampling.sample_key("mq1", "s1"), old)
    assert await sampling.value_minutes_ago("mq1", "s1", minutes=5) == 50


async def test_sampling_batch_push_and_read(fake_platform_redis):
    import time as _t
    import json as _json

    await sampling.push_samples([])  # 空输入不炸
    await sampling.push_samples([("r1", "backlog", 7), ("r1", "added", 42)])
    # 每次写入续 2h TTL：活跃序列不过期，孤儿序列末次推送后自然消亡
    assert (await fake_platform_redis.ttl(sampling.sample_key("r1", "backlog"))) > 0
    pairs = [("r1", "backlog"), ("r1", "added"), ("r2", "backlog")]
    out = await sampling.values_minutes_ago(pairs, minutes=5)
    assert out == {("r1", "backlog"): None, ("r1", "added"): None, ("r2", "backlog"): None}

    # 各序列手写 6 分钟前的旧样本
    r = fake_platform_redis
    for series, v in (("backlog", 5), ("added", 40)):
        await r.lpush(sampling.sample_key("r1", series), _json.dumps({"ts": int(_t.time() - 360), "v": v}))
    out = await sampling.values_minutes_ago(pairs, minutes=5)
    assert out[("r1", "backlog")] == 5
    assert out[("r1", "added")] == 40
    assert out[("r2", "backlog")] is None


# ---------- API（stub provider） ----------


class StubProvider:
    def __init__(self, config):
        pass

    async def get_overview(self):
        return provider.normalize_broker(BROKER_ATTRS) | {"jvm": provider.normalize_jvm({}, {}, {})}

    async def get_queues(self):
        return provider.normalize_queues(QUEUE_VALUE)

    async def get_addresses(self):
        return []

    async def run_test(self):
        return "Jolokia OK, Artemis 2.44.0"


@pytest.fixture
async def client(fake_platform_redis, monkeypatch):
    monkeypatch.setattr(service, "_build_provider", lambda config: StubProvider(config))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/sites", json={"id": "sz", "name": "S"})
        r = await c.post("/api/sites/sz/mq", json={"id": "mq1", "name": "mq1", "host": "target"})
        assert r.status_code == 201
        yield c


async def test_overview_api(client):
    r = await client.get("/api/sites/sz/mq/mq1/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "STARTED"
    assert "jvm" in body


async def test_queues_api_with_diagnosis(client):
    r = await client.get("/api/sites/sz/mq/mq1/queues")
    assert r.status_code == 200
    q1 = r.json()[0]
    assert q1["name"] == "q1"
    assert q1["diagnosis"]["status"] == "WARNING"  # 12381 backlog + 0 consumer
    assert any(i["type"] == "NO_CONSUMER" for i in q1["diagnosis"]["issues"])


async def test_queues_api_5m_trend(client, fake_platform_redis):
    import time as _t
    import json as _json

    # 预置 6 分钟前的 backlog / added 样本：q1 在涨、added 计数倒挂（模拟 broker 重启）
    key = service._series_key("sz", "mq1", "q1")
    for series, v in (("backlog", 12300), ("added", 60000)):
        await fake_platform_redis.lpush(
            sampling.sample_key(key, series), _json.dumps({"ts": int(_t.time() - 360), "v": v}))

    r = await client.get("/api/sites/sz/mq/mq1/queues")
    assert r.status_code == 200
    q1, q2 = r.json()[0], r.json()[1]
    assert q1["backlog_5m_ago"] == 12300
    assert q1["growth_5m"] == 12381 - 12300  # 81
    assert q1["added_5m"] == 0  # added 旧值 60000 > 当前 50000：重启清零，截断为 0
    # 无历史样本的队列：趋势字段为 None（前端显示 '-'），但样本已写入供下次对比
    assert q2["backlog_5m_ago"] is None and q2["growth_5m"] is None and q2["added_5m"] is None
    assert await fake_platform_redis.llen(sampling.sample_key(key, "backlog")) == 2
    key2 = service._series_key("sz", "mq1", "q2")
    assert await fake_platform_redis.llen(sampling.sample_key(key2, "added")) == 1


async def test_queues_api_added_delta(client, fake_platform_redis):
    import time as _t
    import json as _json

    key = service._series_key("sz", "mq1", "q1")
    await fake_platform_redis.lpush(
        sampling.sample_key(key, "added"), _json.dumps({"ts": int(_t.time() - 360), "v": 48000}))
    r = await client.get("/api/sites/sz/mq/mq1/queues")
    assert r.json()[0]["added_5m"] == 50000 - 48000


async def test_queues_api_added_1m(client, fake_platform_redis):
    import time as _t
    import json as _json

    # 预置 70 秒前的 added 样本：够 1 分钟窗口、不够 5 分钟窗口
    key = service._series_key("sz", "mq1", "q1")
    await fake_platform_redis.lpush(
        sampling.sample_key(key, "added"), _json.dumps({"ts": int(_t.time() - 70), "v": 49400}))

    r = await client.get("/api/sites/sz/mq/mq1/queues")
    q1, q2 = r.json()[0], r.json()[1]
    assert q1["added_1m"] == 50000 - 49400  # 600
    assert q1["added_5m"] is None  # 70s 样本不满足 5 分钟窗口
    assert q2["added_1m"] is None  # 无 1 分钟历史（预热）


async def test_values_minutes_ago_sparse_reference_returns_none(client, fake_platform_redis):
    """窗口容差：参考样本老于 1.5 倍窗口时返回 None（不虚报跨窗口增量）。

    回归守卫：刚打开页面/序列刚建立时采样稀疏，若拿几分钟前的旧样本做
    60s 差值，会把跨多分钟的增量误报成 1m 新增（用户看到的"一直递增"）。
    """
    import time as _t
    import json as _json

    key = "res:under-test"
    # 200s 前的唯一样本：超出 1m 窗口的 1.5 倍容差（90s）→ None
    await fake_platform_redis.lpush(
        sampling.sample_key(key, "added"), _json.dumps({"ts": int(_t.time() - 200), "v": 100}))
    out = await sampling.values_minutes_ago([(key, "added")], minutes=1)
    assert out[(key, "added")] is None

    # 70s 前样本落在 [60s, 90s] 容差内 → 正常返回
    await fake_platform_redis.lpush(
        sampling.sample_key(key, "added"), _json.dumps({"ts": int(_t.time() - 70), "v": 160}))
    out = await sampling.values_minutes_ago([(key, "added")], minutes=1)
    assert out[(key, "added")] == 160


async def test_mq_tester(client):
    r = await client.post("/api/test-connection", json={"type": "mq", "config": {"host": "target"}})
    assert r.status_code == 200
    assert r.json()["message"] == "Jolokia OK, Artemis 2.44.0"


async def test_unknown_mq_404(client):
    r = await client.get("/api/sites/sz/mq/nope/overview")
    assert r.status_code == 404
