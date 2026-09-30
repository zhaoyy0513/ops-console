"""僵尸进程监控/终止：列表解析、metrics 计数、pid 校验（防注入）、kill 记 oplog。"""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core import oplog
from backend.app.main import app

# 全量 ps 假输出：表头（应被跳过）+ 存活父进程行 + 两个父进程下的僵尸 + 父进程已退出的孤儿僵尸
ZOMBIE_PS = (
    "  PID  PPID  STAT  ARGS\n"
    " 1001     1 Ss    /usr/sbin/sshd -D\n"
    " 2002     1 S     /usr/bin/python2 app.py --worker\n"
    " 4242  1001 Z+    [chrome_crash] <defunct>\n"
    " 4243  1001 Z     [chrome_crash] <defunct>\n"
    " 5252  2002 Zs    [python2] <defunct>\n"
    " 6363  9999 Z+    [orphan] <defunct>\n"
)


@pytest.fixture
async def env(fake_platform_redis, monkeypatch):
    """patch asyncssh.connect（server provider 是 await connect 后 conn.run）：按命令返回假 stdout。

    yields (client, executed)：executed 记录实际下发的命令，供 kill 用例断言。
    """
    import asyncssh

    executed: list[str] = []

    class FakeResult:
        def __init__(self, stdout: str):
            self.stdout = stdout

    class FakeConn:
        async def run(self, cmd, check=False):
            executed.append(cmd)
            if "ps -eo" in cmd:  # 僵尸采集命令带 LC_ALL=C 前缀，按子串识别
                return FakeResult(ZOMBIE_PS)
            return FakeResult("")  # kill / 其余白名单命令：无输出即成功

        def close(self):
            pass

        async def wait_closed(self):
            pass

    async def fake_connect(host, **kwargs):
        return FakeConn()

    monkeypatch.setattr(asyncssh, "connect", fake_connect)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/sites", json={"id": "sz", "name": "S"})
        await c.post("/api/sites/sz/servers",
                     json={"id": "srv1", "name": "srv", "host": "10.10.1.10",
                           "username": "u", "password": "p"})
        yield c, executed


async def test_zombies_grouped_by_parent(env):
    """僵尸按父进程分组：count 降序，cmd = 同份 ps 输出中父进程 args；父进程已退出则 ''。"""
    client, _ = env
    r = await client.get("/api/sites/sz/servers/srv1/zombies")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 4
    assert data["groups"] == [
        {"ppid": 1001, "count": 2, "cmd": "/usr/sbin/sshd -D"},
        # count 并列 1 时按 ppid 升序保证稳定；9999 不在 ps 输出 -> cmd 为空
        {"ppid": 2002, "count": 1, "cmd": "/usr/bin/python2 app.py --worker"},
        {"ppid": 9999, "count": 1, "cmd": ""},
    ]


async def test_metrics_include_zombie_count(env):
    """metrics 与僵尸统计同一条 SSH 会话：响应直接带 zombie_count（全量 ps 输出中 stat 以 Z 开头的行数）。"""
    client, executed = env
    r = await client.get("/api/sites/sz/servers/srv1/metrics")
    assert r.status_code == 200
    assert r.json()["zombie_count"] == 4
    assert any("ps -eo" in c for c in executed)  # 僵尸命令并入 metrics 同一 SSH 会话


async def test_kill_rejects_non_numeric_pid(env):
    """pid 必须纯数字：非法值 400，且不触达 SSH（防命令注入）。"""
    client, executed = env
    for bad in ("abc", "4242;reboot"):
        r = await client.post(f"/api/sites/sz/servers/srv1/zombies/{bad}/kill")
        assert r.status_code == 400
        assert r.json()["error_code"] == "INVALID_OPERATION"
    assert not [c for c in executed if c.startswith("kill ")]


async def test_kill_success_records_oplog(env):
    client, executed = env
    r = await client.post("/api/sites/sz/servers/srv1/zombies/4242/kill?comm=chrome_crash")
    assert r.status_code == 200
    assert r.json() == {"killed": True}
    assert "kill -9 4242" in executed

    entry = next(e for e in await oplog.read_recent(5) if e["operation"] == "SERVER_KILL_ZOMBIE")
    assert entry["target"] == "4242 chrome_crash"
    assert entry["params"]["pid"] == 4242
    assert entry["result"] == "SUCCESS"
