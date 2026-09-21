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


async def test_mq_tester(client):
    r = await client.post("/api/test-connection", json={"type": "mq", "config": {"host": "target"}})
    assert r.status_code == 200
    assert r.json()["message"] == "Jolokia OK, Artemis 2.44.0"


async def test_unknown_mq_404(client):
    r = await client.get("/api/sites/sz/mq/nope/overview")
    assert r.status_code == 404
