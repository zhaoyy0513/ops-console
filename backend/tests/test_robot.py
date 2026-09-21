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
