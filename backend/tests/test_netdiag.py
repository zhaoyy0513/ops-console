import asyncio
import socket

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.app.modules.netdiag import provider
from backend.app.modules.netdiag.api import router
from backend.app.modules.sites import service as sites_service


@pytest.fixture
async def client(fake_platform_redis):
    """独立 mount router（模块尚未接入全局注册表）。"""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://10.0.0.5", ("10.0.0.5", 80)),
        ("https://api.example.com", ("api.example.com", 443)),
        ("http://10.0.0.5:8080/api/v1", ("10.0.0.5", 8080)),
        ("https://api.example.com/health?x=1", ("api.example.com", 443)),
        ("10.0.0.5:9000", ("10.0.0.5", 9000)),  # 缺 scheme 也按 netloc 解析
    ],
)
def test_parse_base_url(url, expected):
    assert provider.parse_base_url(url) == expected


@pytest.mark.parametrize("url", ["", "   ", "http://:8080", "http://host:notaport"])
def test_parse_base_url_invalid(url):
    assert provider.parse_base_url(url) is None


async def test_probe_open_port():
    """本地临时监听端口 → 可达。"""
    async def handle(_reader, writer):
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        result = await provider.probe("127.0.0.1", port, timeout=1.0)
    finally:
        server.close()
        await server.wait_closed()
    assert result["ok"] is True
    assert result["error"] is None
    assert result["latency_ms"] >= 0


async def test_probe_closed_port():
    """刚释放的本地端口 → 不可达（拒绝连接），错误原因非空。"""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    result = await provider.probe("127.0.0.1", port, timeout=1.0)
    assert result["ok"] is False
    assert result["error"]


async def test_probe_all_limits_concurrency(monkeypatch):
    """30 个目标同时提交，实际并发不超过 MAX_CONCURRENCY。"""
    state = {"active": 0, "peak": 0}

    async def fake_probe(host, port, timeout=provider.PROBE_TIMEOUT):
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.01)
        state["active"] -= 1
        return {"ok": True, "latency_ms": 1, "error": None}

    monkeypatch.setattr(provider, "probe", fake_probe)
    targets = [{"host": "h", "port": i} for i in range(30)]
    results = await provider.probe_all(targets)
    assert len(results) == 30
    assert state["peak"] <= provider.MAX_CONCURRENCY
    assert state["peak"] > 1  # 确实是并发而非串行


async def test_matrix_site_not_found(client):
    r = await client.get("/api/netdiag/nope/matrix")
    assert r.status_code == 404


async def test_matrix_rows_and_default_ports(client, monkeypatch):
    """servers 缺省 22；devices 从 base_url 解析 host/port；不可达行保留错误原因。"""
    async def fake_probe(host, port, timeout=provider.PROBE_TIMEOUT):
        ok = host == "127.0.0.1"
        return {"ok": ok, "latency_ms": 2, "error": None if ok else "connection refused"}

    monkeypatch.setattr(provider, "probe", fake_probe)
    await sites_service.create_site({"id": "s1", "name": "S1"})
    await sites_service.create_resource(
        "s1", "servers", {"id": "srv1", "name": "web", "host": "127.0.0.1"}
    )
    await sites_service.create_resource(
        "s1", "devices", {"id": "dev1", "name": "cam", "base_url": "https://10.1.2.3/api"}
    )

    rows = (await client.get("/api/netdiag/s1/matrix")).json()
    assert [(r["resource_type"], r["resource_name"]) for r in rows] == [
        ("servers", "web"),
        ("devices", "cam"),
    ]
    server, device = rows
    assert (server["host"], server["port"], server["ok"]) == ("127.0.0.1", 22, True)
    assert (device["host"], device["port"], device["ok"]) == ("10.1.2.3", 443, False)
    assert device["error"] == "connection refused"
