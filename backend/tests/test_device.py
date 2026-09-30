import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.modules.device import service
from backend.app.modules.device.provider import HttpDeviceProvider, normalize_device
from samples_device import ENV12_BODY, ENV50_BODY


# ---------- 现场真实响应映射（环境 50 / 环境 12） ----------


def test_env50_mapping():
    """环境 50 /mission/robot/info/active：records 信封，无 online，坐标位置。"""
    raw = ENV50_BODY["records"][0]
    r = normalize_device(raw)
    assert r["id"] == "asrs23"  # robotCode（上游字段）优先于数字 id
    assert r["name"] == "RB-23"
    assert r["battery"] == 82
    assert r["station"] == "(22,65)"  # x/y 坐标
    assert r["status"] == 1  # 无 online 字段 -> 原始 status 不猜语义
    assert r["last_update"].startswith("2025-")  # createDate epoch ms -> ISO


def test_env12_mapping():
    """环境 12 /mission/agent/list：result 信封 + online 语义转换。"""
    r1 = normalize_device(ENV12_BODY["result"][0])
    assert r1["id"] == "sim001"
    assert r1["status"] == "online"  # online:1
    assert r1["station"] == "(33,37)"
    assert r1["error"] is None

    r2 = normalize_device(ENV12_BODY["result"][1])
    assert r2["status"] == "offline"  # online:0
    assert r2["error"] == "E102"


def test_unwrap_env_envelopes():
    assert HttpDeviceProvider._unwrap_list(ENV50_BODY)[0]["robotCode"] == "asrs23"
    assert HttpDeviceProvider._unwrap_list(ENV12_BODY)[0]["robotCode"] == "sim001"
    # 自动探测未知信封
    assert HttpDeviceProvider._unwrap_list({"weird": [{"a": 1}]}) == [{"a": 1}]
    assert HttpDeviceProvider._unwrap_list({"no_list": 1}) == []


# ---------- 通用字段映射（camel/snake） ----------


def test_normalize_device_camel_case():
    r = normalize_device({
        "robotId": "R001", "robotName": "alpha", "state": "running",
        "batteryLevel": 87, "currentStation": "S3", "currentTask": "deliver",
        "lastUpdate": "2026-09-21T10:00:00",
    })
    assert r["name"] == "alpha" and r["status"] == "running"
    assert r["station"] == "S3"


def test_normalize_device_snake_case_and_missing():
    r = normalize_device({"id": "R2", "status": "idle", "battery_level": 50})
    assert r["battery"] == 50 and r["error"] is None


def test_template_multi_field_braces():
    """模板占位符：{f} 单字段；{f1,f2} 多字段逗号连接；缺失字段空串。"""
    raw = {"mapId": 1, "areaId": 2, "name": "dev"}
    r = normalize_device(raw, field_map={
        "station": "({mapId},{areaId})",          # 每个字段各占一个花括号
        "name": "{mapId,areaId}",                  # 多字段合一个花括号
    })
    assert r["station"] == "(1,2)"
    assert r["name"] == "1,2"
    # 缺失字段替换为空串；无花括号整串按字段名直取
    r2 = normalize_device(raw, field_map={"station": "{mapId},{missing}"})
    assert r2["station"] == "1,"
    r3 = normalize_device(raw, field_map={"station": "mapId"})
    assert r3["station"] == 1
    assert normalize_device({})["id"] is None


# ---------- Provider 解包 + API ----------


class StubProvider:
    def __init__(self, config):
        pass

    async def get_device_list(self):
        return [normalize_device({"id": "R001", "name": "alpha", "status": "running",
                                  "battery": 87, "station": "S3", "task": "deliver"}),
                normalize_device({"id": "R002", "name": "beta", "status": "error",
                                  "error": "lidar offline"})]

    async def get_device_detail(self, device_id):
        if device_id != "R001":
            raise service.OpsError("REMOTE_BAD_RESPONSE", "device not found", status_code=502)
        return normalize_device({"id": "R001", "name": "alpha", "status": "running",
                                 "battery": 87, "station": "S3", "task": "deliver",
                                 "position": "x12,y8"})

    async def run_test(self):
        return "Device API OK, 2 devices"


@pytest.fixture
async def client(fake_platform_redis, monkeypatch):
    monkeypatch.setattr(service, "_build_provider", lambda config: StubProvider(config))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/sites", json={"id": "sz", "name": "S"})
        r = await c.post("/api/sites/sz/device-instances", json={"id": "rc1", "name": "rc1", "base_url": "http://device-api"})
        assert r.status_code == 201
        yield c


async def test_list_devices(client):
    r = await client.get("/api/sites/sz/devices")
    assert r.status_code == 200
    items = r.json()
    assert [i["id"] for i in items] == ["R001", "R002"]
    assert items[1]["error"] == "lidar offline"
    assert items[0]["instance"] == "rc1"


async def test_device_detail(client):
    r = await client.get("/api/sites/sz/devices/R001")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "alpha" and body["battery"] == 87


async def test_device_detail_not_found(client):
    r = await client.get("/api/sites/sz/devices/NOPE")
    assert r.status_code == 502  # provider 报错透传


async def test_device_tester(client):
    r = await client.post("/api/test-connection",
                          json={"type": "device", "config": {"base_url": "http://x"}})
    assert r.status_code == 200
    assert r.json()["message"] == "Device API OK, 2 devices"


async def test_provider_requires_base_url():
    with pytest.raises(Exception):
        HttpDeviceProvider({})


def test_value_map_enum_translation():
    """值->展示映射：数字/字符串键互通，未命中保留原值。"""
    vm = {"status": {"1": "CREATE", "2": "Free", "4": "Busy"}}
    assert normalize_device({"robotCode": "R1", "status": 1}, None, vm)["status"] == "CREATE"
    assert normalize_device({"robotCode": "R1", "status": "2"}, None, vm)["status"] == "Free"
    assert normalize_device({"robotCode": "R1", "status": 4}, None, vm)["status"] == "Busy"
    assert normalize_device({"robotCode": "R1", "status": 9}, None, vm)["status"] == 9  # 未命中原样
    assert normalize_device({"robotCode": "R1", "status": 1}, None, None)["status"] == 1  # 未配置


def test_value_map_independent_per_instance():
    """实例独立性：同字段不同实例的映射互不影响（配置随实例存储）。"""
    vm_a = {"status": {"1": "CREATE"}}
    vm_b = {"status": {"1": "ONLINE"}}
    assert normalize_device({"id": "a", "status": 1}, None, vm_a)["status"] == "CREATE"
    assert normalize_device({"id": "b", "status": 1}, None, vm_b)["status"] == "ONLINE"
    # 无 value_map 的实例不受影响
    assert normalize_device({"id": "c", "status": 1})["status"] == 1


# ---------- 自定义字段（custom_fields） ----------


def test_normalize_custom_fields():
    """自定义字段与内置同规则：bind/模板取值（模板优先）-> 值映射，产出在稳定 key 下。"""
    cfs = [
        {"key": "cf_t1", "label_zh": "任务", "label_en": "Task", "bind": "currentTask"},
        {"key": "cf_p1", "label_zh": "坐标", "label_en": "Pos", "template": "({x},{y})"},
        {"key": "cf_s1", "label_zh": "状态", "label_en": "St", "bind": "st",
         "value_map": {"1": "ON"}},
    ]
    r = normalize_device(
        {"id": "R1", "currentTask": "deliver", "x": 3, "y": 7, "st": 1}, None, None, cfs)
    assert r["cf_t1"] == "deliver"
    assert r["cf_p1"] == "(3,7)"
    assert r["cf_s1"] == "ON"  # 数字值与字符串键互通
    assert "cf_t1" not in normalize_device({"id": "R1"})  # 未配置不产出


async def test_custom_field_in_list_response(client, fake_platform_redis, monkeypatch):
    """自定义字段配置经存储 -> normalize -> 列表响应带映射值。"""
    class CfProvider(StubProvider):
        def __init__(self, config):
            self._cf = config.get("custom_fields")

        async def get_device_list(self):
            return [normalize_device(
                {"id": "R001", "name": "alpha", "status": "running", "task": "deliver"},
                None, None, self._cf)]

    monkeypatch.setattr(service, "_build_provider", lambda config: CfProvider(config))
    r = await client.put("/api/sites/sz/device-instances/rc1", json={
        "custom_fields": [{"key": "cf_t1", "label_zh": "任务", "label_en": "Task", "bind": "task"}]})
    assert r.status_code == 200
    saved = r.json()["custom_fields"]
    assert saved[0]["key"] == "cf_t1" and "bind" in saved[0]  # 未知字段已剥离
    r = await client.get("/api/sites/sz/devices?instance=rc1")
    assert r.status_code == 200
    assert r.json()[0]["cf_t1"] == "deliver"


async def test_device_mappings_global_listing(client, fake_platform_redis, monkeypatch):
    """克隆数据源：/devices/mappings 列出全部站点实例的映射配置（不分站点）。"""
    monkeypatch.setattr(service, "_build_provider", lambda config: StubProvider(config))
    await client.post("/api/sites", json={"id": "s1", "name": "S1"})
    await client.post("/api/sites", json={"id": "s2", "name": "S2"})
    await client.post("/api/sites/s1/device-instances", json={
        "id": "ra", "name": "A", "base_url": "http://x",
        "field_map": {"status": "st"}, "value_map": {"status": {"1": "ON"}}})
    await client.post("/api/sites/s2/device-instances", json={"id": "rb", "name": "B", "base_url": "http://y"})

    r = await client.get("/api/devices/mappings")
    assert r.status_code == 200
    items = {x["device_id"]: x for x in r.json()}
    # rc1 来自 client fixture 的种子实例
    assert set(items) == {"ra", "rb", "rc1"}  # 跨站点聚合
    assert items["ra"]["field_map"] == {"status": "st"}
    assert items["ra"]["value_map"] == {"status": {"1": "ON"}}
    assert items["ra"]["site_name"] == "S1"
    assert items["rb"]["field_map"] is None
    assert items["rc1"]["field_map"] is None
