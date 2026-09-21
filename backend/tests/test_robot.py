import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.modules.robot import service
from backend.app.modules.robot.provider import HttpRobotProvider, normalize_robot


# ---------- 字段映射（宽容候选，PRD §12 业务层隔离） ----------


def test_normalize_robot_camel_case():
    r = normalize_robot({
        "robotId": "R001", "robotName": "alpha", "state": "running",
        "batteryLevel": 87, "currentStation": "S3", "currentTask": "deliver",
        "lastUpdate": "2026-09-21T10:00:00",
    })
    assert r["id"] == "R001" and r["name"] == "alpha" and r["status"] == "running"
    assert r["battery"] == 87 and r["station"] == "S3" and r["task"] == "deliver"


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
