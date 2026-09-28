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

    class _Stdin:
        def __init__(self):
            self.data = []

        def write(self, s):
            self.data.append(s)

        def write_eof(self):
            pass

    class FakeProc:
        def __init__(self):
            self.stdin = _Stdin()

        async def communicate(self):
            return FakeResult.stdout, FakeResult.stderr

        def kill(self):
            pass

        def close(self):
            pass

    class FakeConn:
        async def run(self, cmd, input=None, env=None):
            assert input is not None  # 脚本经 stdin 传给 bash -s
            return FakeResult()

        async def create_process(self, cmd, env=None):
            return FakeProc()

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


async def test_validate_cron_and_schedule_fields(client, fake_platform_redis, monkeypatch):
    """cron 校验（未来 3 次）+ 定时字段随脚本存储。"""
    r = await client.post("/api/ssh/validate-cron", json={"cron": "0 2 * * *"})
    assert r.status_code == 200
    assert len(r.json()["next_runs"]) == 3

    r = await client.post("/api/ssh/validate-cron", json={"cron": "bad cron"})
    assert r.status_code == 400

    # 定时脚本落库：cron + sched_enabled 默认 False（新建不自动执行）
    r = await client.post("/api/sites/sz/ssh_scripts", json={
        "id": "cron-job", "name": "cron-job", "server_id": "srv1",
        "content": "echo hi", "cron": "*/5 * * * *"})
    assert r.status_code == 201
    assert r.json()["sched_enabled"] is False

    # 打开开关 → 调度注册
    r = await client.put("/api/sites/sz/ssh_scripts/cron-job",
                         json={"sched_enabled": True})
    assert r.json()["sched_enabled"] is True


async def test_run_adhoc_no_persist(client, fake_platform_redis, monkeypatch):
    """编辑弹窗测试：直接执行表单内容，不创建脚本记录。"""
    import asyncssh
    from backend.app.modules.ssh import service as svc

    class R:
        stdout = "adhoc-ok\n"
        stderr = ""

    class P:
        class _Stdin:
            def write(self, s):
                pass

            def write_eof(self):
                pass

        stdin = None

        def __init__(self):
            self.stdin = P._Stdin()

        async def communicate(self):
            return R.stdout, R.stderr

        def kill(self):
            pass

        def close(self):
            pass

    class C:
        async def run(self, cmd, input=None, env=None):
            assert input == "echo hi"
            return R()

        async def create_process(self, cmd, env=None):
            return P()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(asyncssh, "connect", lambda *a, **k: C())
    async def fake_raw(sid, t, rid):
        return {"host": "1.1.1.1", "port": 22, "username": "u", "password": "p"}

    monkeypatch.setattr(svc, "get_resource_raw", fake_raw)

    r = await client.post("/api/sites/sz/ssh_scripts/run-adhoc",
                          json={"server_id": "srv1", "content": "echo hi"})
    assert r.status_code == 200
    assert "adhoc-ok" in r.json()["stdout"]
    # 未落库：脚本列表不新增
    assert (await client.get("/api/sites/sz/ssh_scripts")).json() == []
