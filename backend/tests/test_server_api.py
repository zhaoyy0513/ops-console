import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.modules.server import service as server_service
from backend.app.shared.errors import OpsError

from backend.app.modules.server.provider import (
    parse_boot_time,
    parse_capabilities,
    parse_cpu,
    parse_diskstats,
    parse_failed_units,
    parse_file_nr,
    parse_oom_events,
    parse_uptime_text,
)


def test_parse_diskstats_excludes_partitions_and_loop():
    """分区（sda1 / nvme0n1p1）与 loop 不计入，避免与整盘双重计数。"""
    sample = (
        "   8       0 sda 100 0 2000 5 200 0 4000 8 0 10 10\n"
        "   8       1 sda1 50 0 1000 2 100 0 2000 4 0 5 5\n"
        "   7       0 loop0 5 0 10 1 0 0 0 0 0 1 1\n"
        " 259       0 nvme0n1 300 0 6000 9 400 0 8000 12 0 20 20\n"
        " 259       1 nvme0n1p1 50 0 1000 2 100 0 2000 4 0 5 5\n"
    )
    assert parse_diskstats(sample) == {
        "read_bytes": (2000 + 6000) * 512,
        "write_bytes": (4000 + 8000) * 512,
        "read_iops": 100 + 300,
        "write_iops": 200 + 400,
    }


def test_parse_diskstats_counts_dm_device_when_it_is_the_only_disk():
    """容器/device-mapper 场景：设备名不在 sda/nvme 白名单时也要采集（否则整卡永远 ?）。"""
    sample = " 253       0 dm-0 10 0 2000 5 20 0 4000 8 0 10 10 0 0 0 0\n"
    assert parse_diskstats(sample) == {
        "read_bytes": 2000 * 512,
        "write_bytes": 4000 * 512,
        "read_iops": 10,
        "write_iops": 20,
    }


def test_parse_diskstats_empty_returns_none():
    """完全无可用设备 → None（前端显示 ?，不误报 0）。"""
    assert parse_diskstats("") is None
    assert parse_diskstats("   7       0 loop0 5 0 10 1 0 0 0 0 0 1 1\n") is None


@pytest.fixture
async def client(fake_platform_redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _seed(client):
    await client.post("/api/sites", json={"id": "sz-test", "name": "深圳测试站"})
    r = await client.post(
        "/api/sites/sz-test/servers",
        json={"id": "srv-01", "name": "srv", "host": "1.2.3.4", "username": "u", "password": "p"},
    )
    assert r.status_code == 201


class FakeProvider:
    calls = 0

    def __init__(self, config: dict):
        pass

    async def get_metrics(self):
        type(self).calls += 1
        await asyncio.sleep(0.05)
        return {"cpu": {"usage": 50.0}}

    async def get_processes(self):
        type(self).calls += 1
        await asyncio.sleep(0.05)
        return [{"pid": 1}]

    async def run_test(self):
        type(self).calls += 1
        await asyncio.sleep(0.01)
        return "SSH OK, 4 cores"


@pytest.fixture
def fake_provider(monkeypatch):
    FakeProvider.calls = 0
    monkeypatch.setattr(server_service, "_build_provider", lambda config: FakeProvider(config))
    return FakeProvider


async def test_concurrent_requests_single_ssh(client, fake_provider):
    """PRD §15：并发 10 次同一 server 查询只产生 1 次 SSH。"""
    await _seed(client)

    async def one():
        return await client.get("/api/sites/sz-test/servers/srv-01/metrics")

    responses = await asyncio.gather(*(one() for _ in range(10)))
    assert all(r.status_code == 200 for r in responses)
    assert fake_provider.calls == 1


async def test_metrics_and_processes_cached_separately(client, fake_provider):
    await _seed(client)
    await client.get("/api/sites/sz-test/servers/srv-01/metrics")
    await client.get("/api/sites/sz-test/servers/srv-01/metrics")
    assert fake_provider.calls == 1
    await client.get("/api/sites/sz-test/servers/srv-01/processes")
    assert fake_provider.calls == 2


async def test_ssh_failure_returns_envelope(client, fake_provider, monkeypatch):
    """验收 7：查询失败不 500，统一错误包络。"""
    await _seed(client)

    async def boom(self):
        raise OpsError("REMOTE_CONNECTION_FAILED", "Unable to connect to server", "srv-01")

    monkeypatch.setattr(fake_provider, "get_metrics", boom)
    r = await client.get("/api/sites/sz-test/servers/srv-01/metrics")
    assert r.status_code == 502
    body = r.json()
    assert body["success"] is False
    assert body["error_code"] == "REMOTE_CONNECTION_FAILED"
    assert body["resource"] == "srv-01"


async def test_unknown_server_404(client, fake_provider):
    r = await client.get("/api/sites/sz-test/servers/nope/metrics")
    assert r.status_code == 404


async def test_server_connection_tester(client, fake_provider):
    await _seed(client)
    r = await client.post(
        "/api/test-connection",
        json={"type": "server", "config": {"host": "1.2.3.4", "username": "u"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "SSH OK" in body["message"]


# ---------- 纯函数解析（不 mock SSH） ----------

TOP_SAMPLE = """top - 10:12:30 up 37 days,  4:21,  2 users,  load average: 0.00, 0.01, 0.05
Tasks: 120 total,   1 running, 119 sleeping,   0 stopped,   0 zombie
%Cpu(s):  0.5 us,  0.3 sy,  0.0 ni, 98.7 id,  0.5 wa,  0.0 hi,  0.0 si,  0.0 st
MiB Mem :  15884.0 total,   5123.0 free,   6102.0 used,   4659.0 buff/cache
MiB Swap:   2048.0 total,   2048.0 free,      0.0 used.  9312.0 avail Mem

top - 10:12:31 up 37 days,  4:21,  2 users,  load average: 0.10, 0.03, 0.06
Tasks: 120 total,   2 running, 118 sleeping,   0 stopped,   0 zombie
%Cpu(s):  6.0 us,  2.0 sy,  0.0 ni, 90.0 id,  2.0 wa,  0.0 hi,  0.0 si,  7.5 st
"""


def test_parse_cpu_includes_steal_from_last_frame():
    """st 是 Cpu 行最后一列（行尾无逗号），且多帧取最后一帧。"""
    assert parse_cpu(TOP_SAMPLE) == {"usage": 10.0, "iowait": 2.0, "steal": 7.5}


def test_parse_cpu_empty_returns_none_fields():
    assert parse_cpu("") == {"usage": None, "iowait": None, "steal": None}


def test_parse_failed_units():
    sample = (
        "nginx.service            loaded failed failed A high performance web server\n"
        "redis-server.service     loaded failed failed Advanced key-value store\n"
        "__OK__\n"
    )
    assert parse_failed_units(sample) == [
        {"unit": "nginx.service", "description": "A high performance web server"},
        {"unit": "redis-server.service", "description": "Advanced key-value store"},
    ]


def test_parse_failed_units_empty_output_is_empty_list():
    """没有失败单元时 systemctl 输出为空（只有标记行）-> []，不是 None。"""
    assert parse_failed_units("") == []
    assert parse_failed_units("__OK__\n") == []


def test_parse_oom_events_both_timestamp_formats():
    sample = (
        "[Mon Oct 27 10:12:33 2026] Out of memory: Killed process 1234 (java) "
        "total-vm:2048kB, anon-rss:1024kB\n"
        "Oct 26 03:00:01 web1 kernel: Out of memory: Kill process 99 (mysqld) "
        "score 500 or sacrifice child\n"
    )
    rows = parse_oom_events(sample)
    assert [r["process"] for r in rows] == ["java", "mysqld"]
    assert rows[0]["time"] == "Mon Oct 27 10:12:33 2026"
    assert rows[1]["time"] == "Oct 26 03:00:01"
    assert "Killed process 1234" in rows[0]["detail"]


def test_parse_oom_events_empty_and_unrelated_lines():
    assert parse_oom_events("") == []
    assert parse_oom_events("Oct 26 03:00:01 web1 kernel: usb 1-1: new device\n") == []


def test_parse_file_nr():
    assert parse_file_nr("  1600\t0\t8000\n") == {"allocated": 1600, "max": 8000, "percent": 20.0}


def test_parse_file_nr_bad_input_returns_none():
    assert parse_file_nr("") is None
    assert parse_file_nr("not a number") is None
    assert parse_file_nr("100\t0\t0") is None  # 上限为 0 不能当除数


def test_parse_uptime_text():
    assert parse_uptime_text(
        " 10:12:33 up 37 days,  4:21,  2 users,  load average: 0.00, 0.01, 0.05"
    ) == "37 days, 4:21"
    # 单数 user / 无 users 段（busybox）都要能取
    assert parse_uptime_text(
        " 10:12:33 up 5 min,  1 user,  load average: 0.1, 0.2, 0.3"
    ) == "5 min"
    assert parse_uptime_text(" 10:12:33 up 2 days,  1:02,  load average: 0.0, 0.0, 0.0") == (
        "2 days, 1:02"
    )
    assert parse_uptime_text("") is None


def test_parse_boot_time():
    assert parse_boot_time("         system boot  2026-10-20 10:12\n") == "2026-10-20T10:12:00"
    assert parse_boot_time("") is None  # 容器内 who -b 常为空


def test_parse_capabilities():
    sample = {
        "uid": "1000\n",
        "psi": "ok\n",
        "dmesg": "no\n",
        "systemctl": "ok\n",
        "kernlog": "no\n",
        "syslog": "ok\n",
    }
    assert parse_capabilities(sample) == {
        "root": False,
        "psi": True,
        "dmesg": False,
        "systemctl": True,
        "kernlog": False,
        "syslog": True,
    }
    assert parse_capabilities({"uid": "0\n"}) == {
        "root": True,
        "psi": False,
        "dmesg": False,
        "systemctl": False,
        "kernlog": False,
        "syslog": False,
    }
