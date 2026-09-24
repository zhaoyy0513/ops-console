import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest.fixture
async def client(fake_platform_redis, monkeypatch):
    # run_script 用真实 SSH 配置——测试里 patch 掉 asyncssh 连接
    import asyncssh
    from backend.app.modules.ssh import service

    class FakeResult:
        stdout = "hello from bash\n"
        stderr = ""

    class FakeConn:
        async def run(self, cmd, stdin=None):
            assert stdin is not None  # 脚本经 stdin 传给 bash -s
            return FakeResult()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    def fake_connect(host, **kwargs):
        assert host == "10.10.1.10"  # 绑定 server 的 host
        return FakeConn()

    monkeypatch.setattr(asyncssh, "connect", fake_connect)
    monkeypatch.setattr(service, "RUN_TIMEOUT", 5)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/sites", json={"id": "sz", "name": "S"})
        await c.post("/api/sites/sz/servers",
                     json={"id": "srv1", "name": "srv", "host": "10.10.1.10",
                           "username": "u", "password": "p"})
        yield c


async def test_script_crud_and_run(client):
    # 创建脚本（绑定 srv1）
    r = await client.post("/api/sites/sz/ssh_scripts", json={
        "name": "disk-check", "server_id": "srv1", "content": "echo hello from bash"})
    assert r.status_code == 201
    sid = r.json()["id"]

    # 列表
    r = await client.get("/api/sites/sz/ssh_scripts")
    assert [x["name"] for x in r.json()] == ["disk-check"]

    # 更新
    r = await client.put(f"/api/sites/sz/ssh_scripts/{sid}",
                         json={"content": "echo updated"})
    assert r.json()["content"] == "echo updated"

    # 执行（fake conn 断言 host 来自绑定的 server 配置）
    r = await client.post(f"/api/sites/sz/ssh_scripts/{sid}/run")
    assert r.status_code == 200
    body = r.json()
    assert "hello from bash" in body["stdout"] or "updated" in body["stdout"]
    assert body["timed_out"] is False

    # 删除
    assert (await client.delete(f"/api/sites/sz/ssh_scripts/{sid}")).status_code == 204
    assert (await client.get("/api/sites/sz/ssh_scripts")).json() == []
