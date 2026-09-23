import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.modules.robot import service
from backend.app.modules.robot.provider import HttpRobotProvider, normalize_robot
from samples_robot import ENV12_BODY, ENV50_BODY


# ---------- 现场真实响应映射（环境 50 / 环境 12） ----------


def test_env50_mapping():
    """环境 50 /mission/robot/info/active：records 信封，无 online，坐标位置。"""
    raw = ENV50_BODY["records"][0]
    r = normalize_robot(raw)
    assert r["id"] == "asrs23"  # robotCode 优先于数字 id
    assert r["name"] == "RB-23"
    assert r["battery"] == 82
    assert r["station"] == "(22,65)"  # x/y 坐标
    assert r["status"] == 1  # 无 online 字段 -> 原始 status 不猜语义
    assert r["last_update"].startswith("2025-")  # createDate epoch ms -> ISO


def test_env12_mapping():
    """环境 12 /mission/agent/list：result 信封 + online 语义转换。"""
    r1 = normalize_robot(ENV12_BODY["result"][0])
    assert r1["id"] == "sim001"
    assert r1["status"] == "online"  # online:1
    assert r1["station"] == "(33,37)"
    assert r1["error"] is None

    r2 = normalize_robot(ENV12_BODY["result"][1])
    assert r2["status"] == "offline"  # online:0
    assert r2["error"] == "E102"


def test_unwrap_env_envelopes():
    assert HttpRobotProvider._unwrap_list(ENV50_BODY)[0]["robotCode"] == "asrs23"
    assert HttpRobotProvider._unwrap_list(ENV12_BODY)[0]["robotCode"] == "sim001"
    # 自动探测未知信封
    assert HttpRobotProvider._unwrap_list({"weird": [{"a": 1}]}) == [{"a": 1}]
    assert HttpRobotProvider._unwrap_list({"no_list": 1}) == []


# ---------- 通用字段映射（camel/snake） ----------


def test_normalize_robot_camel_case():
    r = normalize_robot({
        "robotId": "R001", "robotName": "alpha", "state": "running",
        "batteryLevel": 87, "currentStation": "S3", "currentTask": "deliver",
        "lastUpdate": "2026-09-21T10:00:00",
    })
    assert r["name"] == "alpha" and r["status"] == "running"
    assert r["station"] == "S3" and r["task"] == "deliver"


def test_normalize_robot_snake_case_and_missing():
    r = normalize_robot({"id": "R2", "status": "idle", "battery_level": 50})
    assert r["battery"] == 50 and r["task"] is None and r["error"] is None
    assert normalize_robot({})["id"] is None


# ---------- Provider 解包 + API ----------


class StubProvider:
    def __init__(self, config):
        pass

    async def get_robot_list(self):
        return [normalize_robot({"id": "R001", "name": "alpha", "status": "running",
                                 "battery": 87, "station": "S3", "task": "deliver"}),
                normalize_robot({"id": "R002", "name": "beta", "status": "error",
                                 "error": "lidar offline"})]

    async def get_robot_detail(self, robot_id):
        if robot_id != "R001":
            raise service.OpsError("REMOTE_BAD_RESPONSE", "robot not found", status_code=502)
        return normalize_robot({"id": "R001", "name": "alpha", "status": "running",
                                "battery": 87, "station": "S3", "task": "deliver",
                                "position": "x12,y8"})

    async def run_test(self):
        return "Robot API OK, 2 robots"


@pytest.fixture
async def client(fake_platform_redis, monkeypatch):
    monkeypatch.setattr(service, "_build_provider", lambda config: StubProvider(config))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/sites", json={"id": "sz", "name": "S"})
        r = await c.post("/api/sites/sz/robot-instances", json={"id": "rc1", "name": "rc1", "base_url": "http://robot-api"})
        assert r.status_code == 201
        yield c


async def test_list_robots(client):
    r = await client.get("/api/sites/sz/robots")
    assert r.status_code == 200
    items = r.json()
    assert [i["id"] for i in items] == ["R001", "R002"]
    assert items[1]["error"] == "lidar offline"
    assert items[0]["instance"] == "rc1"


async def test_robot_detail(client):
    r = await client.get("/api/sites/sz/robots/R001")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "alpha" and body["battery"] == 87


async def test_robot_detail_not_found(client):
    r = await client.get("/api/sites/sz/robots/NOPE")
    assert r.status_code == 502  # provider 报错透传


async def test_robot_tester(client):
    r = await client.post("/api/test-connection",
                          json={"type": "robot", "config": {"base_url": "http://x"}})
    assert r.status_code == 200
    assert r.json()["message"] == "Robot API OK, 2 robots"


async def test_provider_requires_base_url():
    with pytest.raises(Exception):
        HttpRobotProvider({})


def test_value_map_enum_translation():
    """值->展示映射：数字/字符串键互通，未命中保留原值。"""
    vm = {"status": {"1": "CREATE", "2": "Free", "4": "Busy"}}
    assert normalize_robot({"robotCode": "R1", "status": 1}, None, vm)["status"] == "CREATE"
    assert normalize_robot({"robotCode": "R1", "status": "2"}, None, vm)["status"] == "Free"
    assert normalize_robot({"robotCode": "R1", "status": 4}, None, vm)["status"] == "Busy"
    assert normalize_robot({"robotCode": "R1", "status": 9}, None, vm)["status"] == 9  # 未命中原样
    assert normalize_robot({"robotCode": "R1", "status": 1}, None, None)["status"] == 1  # 未配置


def test_value_map_independent_per_instance():
    """实例独立性：同字段不同实例的映射互不影响（配置随实例存储）。"""
    vm_a = {"status": {"1": "CREATE"}}
    vm_b = {"status": {"1": "ONLINE"}}
    assert normalize_robot({"id": "a", "status": 1}, None, vm_a)["status"] == "CREATE"
    assert normalize_robot({"id": "b", "status": 1}, None, vm_b)["status"] == "ONLINE"
    # 无 value_map 的实例不受影响
    assert normalize_robot({"id": "c", "status": 1})["status"] == 1


async def test_robot_mappings_global_listing(client, fake_platform_redis, monkeypatch):
    """克隆数据源：/robots/mappings 列出全部站点实例的映射配置（不分站点）。"""
    monkeypatch.setattr(service, "_build_provider", lambda config: StubProvider(config))
    await client.post("/api/sites", json={"id": "s1", "name": "S1"})
    await client.post("/api/sites", json={"id": "s2", "name": "S2"})
    await client.post("/api/sites/s1/robot-instances", json={
        "id": "ra", "name": "A", "base_url": "http://x",
        "field_map": {"status": "st"}, "value_map": {"status": {"1": "ON"}}})
    await client.post("/api/sites/s2/robot-instances", json={"id": "rb", "name": "B", "base_url": "http://y"})

    r = await client.get("/api/robots/mappings")
    assert r.status_code == 200
    items = {x["robot_id"]: x for x in r.json()}
    # rc1 来自 client fixture 的种子实例
    assert set(items) == {"ra", "rb", "rc1"}  # 跨站点聚合
    assert items["ra"]["field_map"] == {"status": "st"}
    assert items["ra"]["value_map"] == {"status": {"1": "ON"}}
    assert items["ra"]["site_name"] == "S1"
    assert items["rb"]["field_map"] is None
    assert items["rc1"]["field_map"] is None
