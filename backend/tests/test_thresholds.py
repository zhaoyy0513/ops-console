import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest.fixture
async def client(fake_platform_redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_site_thresholds_roundtrip(client):
    r = await client.post(
        "/api/sites", json={"id": "s1", "name": "S1", "thresholds": {"cpu_warning": 70}}
    )
    assert r.json()["thresholds"] == {"cpu_warning": 70}

    r = await client.put("/api/sites/s1", json={"thresholds": {"cpu_warning": 60, "disk_critical": 92}})
    assert r.json()["thresholds"] == {"cpu_warning": 60, "disk_critical": 92}

    # 清空（null/缺省 = 保留；空对象 = 清除）
    r = await client.put("/api/sites/s1", json={"thresholds": {}})
    assert r.json()["thresholds"] is None


async def test_server_thresholds_roundtrip(client):
    await client.post("/api/sites", json={"id": "s1", "name": "S1"})
    r = await client.post(
        "/api/sites/s1/servers",
        json={"id": "v1", "name": "v1", "host": "1.2.3.4", "thresholds": {"memory_warning": 75}},
    )
    assert r.json()["thresholds"] == {"memory_warning": 75}

    r = await client.put("/api/sites/s1/servers/v1", json={"thresholds": {"memory_critical": 93}})
    # thresholds 整体替换语义；资源>站点>全局的三层合并发生在诊断时
    assert r.json()["thresholds"] == {"memory_critical": 93}
