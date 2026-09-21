import pytest

from backend.app.modules.server import provider
from backend.app.modules.server.provider import (
    COMMANDS,
    SSHServerMetricsProvider,
    merge_disk,
    parse_cpu,
    parse_df,
    parse_load,
    parse_memory,
    parse_network,
    parse_processes,
)

# 真实 Linux 输出样本（C locale）
SAMPLE_TOP = """top - 14:23:01 up 45 days,  3:12,  2 users,  load average: 0.52, 0.58, 0.59
Tasks: 145 total,   1 running, 144 sleeping,   0 stopped,   0 zombie
%Cpu(s):  3.0 us,  1.2 sy,  0.0 ni, 95.0 id,  0.5 wa,  0.0 hi,  0.3 si,  0.0 st
MiB Mem :   3888.0 total,    567.2 free,   1234.5 used,   2086.3 buff/cache
MiB Swap:   2047.0 total,   2047.0 free,      0.0 used. 2345.7 avail Mem
"""

SAMPLE_UPTIME = " 14:23:01 up 45 days,  3:12,  2 users,  load average: 0.52, 0.58, 0.59\n"
SAMPLE_NPROC = "2\n"

SAMPLE_FREE = """              total        used        free      shared  buff/cache   available
Mem:           3888        1234         567         123        2087        2345
Swap:          2047           0        2047
"""

SAMPLE_DF_H = """Filesystem      Size  Used Avail Use% Mounted on
/dev/vda1        40G   20G   20G  50% /
tmpfs           2.0G     0  2.0G   0% /dev/shm
/dev/vdb1       100G   94G  6.0G  95% /data
"""

SAMPLE_DF_I = """Filesystem     Inodes IUsed IFree IUse% Mounted on
/dev/vda1      2560000 51200 2508800    2% /
/dev/vdb1      6553600  1.2M 5341600   19% /data
"""

SAMPLE_NETDEV = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 1234567    9876    0    0    0     0          0         0  1234567    9876    0    0    0     0       0          0
  eth0: 87654321  654321   12   34    0     0          0         0 123456789  765432    5    6    0     0       0          0
  eth1: 1000000    8000    1    2    0     0          0         0   2000000   9000    3    4    0     0       0          0
"""

SAMPLE_PS = """USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
java    123456 87.0 45.2 8192000 2048000 ?       Sl   09:12 100:20 java -jar app.jar
nginx   123457 12.5  1.2  123456  7890 ?        S    09:13   5:00 nginx: worker
root         1  0.0  0.1 123456  6789 ?        Ss   2025   1:00 /sbin/init
"""

SAMPLES = {
    COMMANDS["cpu"]: SAMPLE_TOP,
    COMMANDS["load"]: SAMPLE_UPTIME,
    COMMANDS["cores"]: SAMPLE_NPROC,
    COMMANDS["memory"]: SAMPLE_FREE,
    COMMANDS["disk_usage"]: SAMPLE_DF_H,
    COMMANDS["disk_inode"]: SAMPLE_DF_I,
    COMMANDS["network"]: SAMPLE_NETDEV,
    COMMANDS["processes"]: SAMPLE_PS,
}


# ---------- 解析器 ----------


def test_parse_cpu():
    assert parse_cpu(SAMPLE_TOP) == {"usage": 5.0, "iowait": 0.5}


def test_parse_cpu_missing_fields():
    assert parse_cpu("no cpu line here") == {"usage": None, "iowait": None}


def test_parse_load():
    assert parse_load(SAMPLE_UPTIME) == {"load1": 0.52, "load5": 0.58, "load15": 0.59}


def test_parse_load_missing():
    assert parse_load("up 5 min") == {"load1": None, "load5": None, "load15": None}


def test_parse_memory():
    assert parse_memory(SAMPLE_FREE) == {
        "total": 3888,
        "used": 1234,
        "available": 2345,
        "cached": 2087,
        "swap_total": 2047,
        "swap_used": 0,
    }


def test_parse_memory_missing_swap():
    text = "Mem:           3888        1234         567         123        2087        2345\n"
    parsed = parse_memory(text)
    assert parsed["total"] == 3888
    assert parsed["swap_total"] is None


def test_parse_df():
    rows = parse_df(SAMPLE_DF_H)
    assert [r["mount"] for r in rows] == ["/", "/dev/shm", "/data"]
    assert rows[2] == {
        "filesystem": "/dev/vdb1",
        "size": "100G",
        "used": "94G",
        "avail": "6.0G",
        "use_percent": 95,
        "mount": "/data",
    }


def test_parse_df_garbage_lines_skipped():
    assert parse_df("Filesystem Size Used Avail Use% Mounted on\ngarbage line\n") == []


def test_merge_disk():
    merged = merge_disk(parse_df(SAMPLE_DF_H), parse_df(SAMPLE_DF_I))
    data = {m["mount"]: m for m in merged}
    assert data["/"]["use_percent"] == 50
    assert data["/"]["inode_percent"] == 2
    assert data["/data"]["use_percent"] == 95
    assert data["/data"]["inode_percent"] == 19


def test_parse_network_excludes_lo_and_aggregates():
    # eth0 + eth1 聚合：rx=87654321+1000000, tx=123456789+2000000
    # errors=12+5+1+3, dropped=34+6+2+4
    assert parse_network(SAMPLE_NETDEV) == {
        "rx": 88654321,
        "tx": 125456789,
        "errors": 21,
        "dropped": 46,
    }


def test_parse_processes():
    rows = parse_processes(SAMPLE_PS)
    assert rows[0] == {
        "pid": 123456,
        "cpu_percent": 87.0,
        "mem_percent": 45.2,
        "command": "java -jar app.jar",
    }
    assert len(rows) == 3


# ---------- 白名单约束：provider 只可能执行白名单集合内的命令 ----------


class _FakeResult:
    def __init__(self, stdout: str):
        self.stdout = stdout


class _FakeConn:
    """模拟 asyncssh 连接：await connect() 得到它，且支持 async with。"""

    executed: list[str] = []

    async def run(self, command, *, check=False):
        _FakeConn.executed.append(command)
        return _FakeResult(SAMPLES.get(command, ""))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def __await__(self):
        return self._as_self().__await__()

    async def _as_self(self):
        return self

    def close(self):
        pass

    async def wait_closed(self):
        return None


@pytest.fixture
def fake_ssh(monkeypatch):
    _FakeConn.executed.clear()

    def fake_connect(**kwargs):
        return _FakeConn()

    monkeypatch.setattr(provider.asyncssh, "connect", fake_connect)
    return _FakeConn


async def test_provider_executes_only_whitelisted_commands(fake_ssh):
    p = SSHServerMetricsProvider(
        {"host": "test-host", "port": 22, "username": "u", "password": "p"}
    )
    await p.get_metrics()
    await p.get_processes()
    await p.get_disk()

    assert fake_ssh.executed, "provider should have run commands"
    assert set(fake_ssh.executed) <= set(COMMANDS.values())


async def test_provider_output_structure(fake_ssh):
    p = SSHServerMetricsProvider({"host": "test-host"})
    metrics = await p.get_metrics()
    assert metrics["cpu"]["usage"] == 5.0
    assert metrics["cpu"]["cores"] == 2
    assert metrics["load"]["load1"] == 0.52
    assert metrics["memory"]["total"] == 3888
    assert metrics["network"]["rx"] == 88654321

    processes = await p.get_processes()
    assert processes[0]["pid"] == 123456

    disk = await p.get_disk()
    data = {d["mount"]: d for d in disk}
    assert data["/data"]["use_percent"] == 95
    assert data["/data"]["inode_percent"] == 19
