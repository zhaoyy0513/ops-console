"""日志查看器（P1-11）：CRUD、白名单、shell 转义、窗口解析、权限降级。

全部走纯函数或假 provider——不需要真实 SSH。
"""

import shlex

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.modules.logs import service
from backend.app.modules.logs.provider import (
    MAX_OUTPUT_BYTES,
    META,
    NO_PERM,
    NOT_FILE,
    NOT_FOUND,
    STAT_FAIL,
    build_read_command,
    clamp_lines,
    parse_read_output,
)


@pytest.fixture
async def client(fake_platform_redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _make_site(client, site_id="sz-test"):
    r = await client.post("/api/sites", json={"id": site_id, "name": site_id})
    assert r.status_code == 201


async def _make_server(client, site_id="sz-test"):
    r = await client.post(
        f"/api/sites/{site_id}/servers",
        json={"id": "srv-01", "name": "srv", "host": "1.2.3.4", "username": "u", "password": "p"},
    )
    assert r.status_code == 201


def _meta(size: int, inode: str = "42", off: int = 0, n: int = 0) -> bytes:
    return f"{META}{size} {inode} {off} {n}\n".encode()


# ---------- CRUD ----------


async def test_source_crud_and_label_unique(client):
    await _make_site(client)

    r = await client.post("/api/logs/sz-test", json={"label": "应用日志", "path": "/var/log/app.log"})
    assert r.status_code == 201
    src = r.json()
    assert src["label"] == "应用日志" and src["path"] == "/var/log/app.log"
    assert src["id"]

    listed = (await client.get("/api/logs/sz-test")).json()
    assert [s["id"] for s in listed] == [src["id"]]

    # 同站点 label 唯一
    r = await client.post("/api/logs/sz-test", json={"label": "应用日志", "path": "/var/log/b.log"})
    assert r.status_code == 409

    # 改名冲突 / 正常改名
    b = (await client.post("/api/logs/sz-test", json={"label": "B", "path": "/var/log/b.log"})).json()
    assert (await client.put(f"/api/logs/sz-test/{b['id']}", json={"label": "应用日志"})).status_code == 409
    r = await client.put(f"/api/logs/sz-test/{b['id']}", json={"label": "B2", "path": "/var/log/b2.log"})
    assert r.status_code == 200 and r.json()["label"] == "B2" and r.json()["path"] == "/var/log/b2.log"

    assert (await client.delete(f"/api/logs/sz-test/{src['id']}")).status_code == 204
    assert [s["id"] for s in (await client.get("/api/logs/sz-test")).json()] == [b["id"]]


async def test_path_must_be_absolute(client):
    await _make_site(client)
    for bad in ("relative/app.log", "~/app.log", ""):
        r = await client.post("/api/logs/sz-test", json={"label": "x", "path": bad})
        assert r.status_code == 400


async def test_missing_site_404(client):
    assert (await client.get("/api/logs/no-such")).status_code == 404
    assert (await client.post("/api/logs/no-such",
                              json={"label": "x", "path": "/var/log/x"})).status_code == 404


async def test_source_oplog_lifecycle(client):
    from backend.app.core import oplog

    await _make_site(client)
    src = (await client.post("/api/logs/sz-test",
                             json={"label": "应用日志", "path": "/var/log/app.log"})).json()
    entry = (await oplog.read_recent(1))[0]
    assert entry["operation"] == "LOGS_SOURCE_CREATED"
    assert entry["resource"] == "logs/应用日志"
    assert entry["params"]["source_id"] == src["id"]

    await client.put(f"/api/logs/sz-test/{src['id']}", json={"label": "新名"})
    assert (await oplog.read_recent(1))[0]["operation"] == "LOGS_SOURCE_UPDATED"

    await client.delete(f"/api/logs/sz-test/{src['id']}")
    assert (await oplog.read_recent(1))[0]["operation"] == "LOGS_SOURCE_DELETED"


# ---------- 路径白名单 / 读取编排 ----------


class FakeProvider:
    calls: list[tuple] = []

    def __init__(self, config: dict):
        self.config = config

    async def read(self, path: str, **kwargs):
        type(self).calls.append((path, kwargs))
        return {
            "content": "hello\n",
            "start_offset": 0,
            "next_offset": 6,
            "size": 6,
            "inode": "42",
            "eof": True,
            "truncated": False,
            "error_code": None,
            "error": None,
        }


@pytest.fixture
def fake_provider(monkeypatch):
    FakeProvider.calls = []
    monkeypatch.setattr(service, "SSHLogsProvider", FakeProvider)
    return FakeProvider


async def test_read_uses_configured_path_only(client, fake_provider):
    """前端只能给 source_id；即使带 path 查询参数，provider 也只拿到配置里的路径。"""
    await _make_site(client)
    await _make_server(client)
    src = (await client.post("/api/logs/sz-test",
                             json={"label": "应用日志", "path": "/var/log/app.log"})).json()

    r = await client.get(f"/api/logs/sz-test/{src['id']}/read",
                         params={"mode": "tail", "path": "/etc/shadow"})
    assert r.status_code == 200
    assert r.json()["content"] == "hello\n"
    assert fake_provider.calls[0][0] == "/var/log/app.log"
    assert fake_provider.calls[0][1]["mode"] == "tail"


async def test_read_unknown_source_404(client, fake_provider):
    await _make_site(client)
    await _make_server(client)
    assert (await client.get("/api/logs/sz-test/nope/read")).status_code == 404
    assert fake_provider.calls == []


async def test_read_no_server_is_in_band(client, fake_provider):
    """站点没有 Server：返回 200 + NO_SERVER（页面保留已加载内容），不是 5xx。"""
    await _make_site(client)
    src = (await client.post("/api/logs/sz-test",
                             json={"label": "应用日志", "path": "/var/log/app.log"})).json()
    r = await client.get(f"/api/logs/sz-test/{src['id']}/read")
    assert r.status_code == 200
    body = r.json()
    assert body["error_code"] == "NO_SERVER"
    assert body["content"] == ""
    assert fake_provider.calls == []


async def test_search_requires_keyword(client, fake_provider):
    await _make_site(client)
    await _make_server(client)
    src = (await client.post("/api/logs/sz-test",
                             json={"label": "应用日志", "path": "/var/log/app.log"})).json()
    r = await client.get(f"/api/logs/sz-test/{src['id']}/read", params={"mode": "search"})
    assert r.status_code == 400
    assert fake_provider.calls == []


# ---------- 命令构造：防注入 ----------


def test_build_command_quotes_path():
    path = "/var/log/a b'; rm -rf / #.log"
    cmd = build_read_command(path, "tail")
    first = cmd.splitlines()[0]
    assert first.startswith("P=")
    # 赋值右侧必须被解析为「恰好一个 token，且等于原始路径」
    assert shlex.split(first[2:]) == [path]


def test_build_command_quotes_search_keyword():
    kw = "x'; id; #"
    cmd = build_read_command("/var/log/app.log", "search", kw=kw)
    grep_line = next(line for line in cmd.splitlines() if "grep -n -i" in line)
    tokens = shlex.split(grep_line)
    assert kw in tokens
    assert "id" not in tokens  # 分号没有把 id 拆成独立命令
    assert "rm" not in tokens


def test_build_command_offset_is_zero_based():
    cmd = build_read_command("/var/log/app.log", "offset", offset=10)
    assert "OFF=10;" in cmd
    assert "tail -c +$((OFF+1))" in cmd
    # 负偏移钳到 0
    assert "OFF=0;" in build_read_command("/var/log/app.log", "offset", offset=-5)


def test_build_command_clamps_lines():
    assert "head -n 1000" in build_read_command("/x", "head", lines=99999)
    assert "head -n 1" in build_read_command("/x", "head", lines=0)
    assert clamp_lines(200) == 200


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        build_read_command("/x", "rm-rf")


# ---------- 解析：权限探测降级 ----------


@pytest.mark.parametrize("marker,code", [
    (NOT_FOUND, "NOT_FOUND"),
    (NO_PERM, "NO_PERMISSION"),
    (NOT_FILE, "NOT_A_FILE"),
    (STAT_FAIL, "STAT_FAILED"),
])
def test_probe_failure_degrades_in_band(marker, code):
    out = parse_read_output(marker.encode() + b"\n", "tail")
    assert out["error_code"] == code
    assert out["content"] == ""


def test_unexpected_output_is_bad_response():
    out = parse_read_output(b"bash: syntax error\n", "tail")
    assert out["error_code"] == "BAD_RESPONSE"


# ---------- 解析：各模式偏移 ----------


def test_parse_tail_offsets():
    out = parse_read_output(_meta(100, off=96, n=4) + b"a\nb\n", "tail")
    assert out["content"] == "a\nb\n"
    assert out["start_offset"] == 96
    assert out["next_offset"] == 100
    assert out["eof"] is True
    assert out["truncated"] is False


def test_parse_tail_truncated_keeps_newest_bytes_and_drops_partial_first_line():
    body = b"partial\n" + b"x" * (MAX_OUTPUT_BYTES - 8)
    out = parse_read_output(_meta(1_000_000, n=MAX_OUTPUT_BYTES + 10) + body, "tail")
    assert out["truncated"] is True
    assert out["content"].startswith("x")
    assert out["start_offset"] == 1_000_000 - MAX_OUTPUT_BYTES + len(b"partial\n")
    assert out["next_offset"] == 1_000_000


def test_parse_head_offsets():
    out = parse_read_output(_meta(100) + b"a\nb\n", "head")
    assert out["start_offset"] == 0
    assert out["next_offset"] == 4
    assert out["eof"] is False
    assert parse_read_output(_meta(4) + b"a\nb\n", "head")["eof"] is True


def test_parse_offset_holds_back_partial_trailing_line():
    """跟随/翻页不把半行算进 next_offset——下一次从这半行开头继续读。"""
    out = parse_read_output(_meta(100, off=10) + b"abc\ndef", "offset")
    assert out["content"] == "abc\n"
    assert out["next_offset"] == 14
    assert out["eof"] is False


def test_parse_offset_at_eof():
    out = parse_read_output(_meta(100, off=100) + b"", "offset")
    assert out["next_offset"] == 100
    assert out["eof"] is True


def test_parse_search_truncates_at_100_matches():
    body = b"".join(f"{i}:line\n".encode() for i in range(100))
    out = parse_read_output(_meta(999) + body, "search")
    assert out["truncated"] is False
    assert out["content"].count("\n") == 100

    body = b"".join(f"{i}:line\n".encode() for i in range(101))
    out = parse_read_output(_meta(999) + body, "search")
    assert out["truncated"] is True
    assert out["content"].count("\n") == 100
    assert out["next_offset"] == 999
