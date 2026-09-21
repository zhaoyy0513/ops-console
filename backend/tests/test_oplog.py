import pytest
from fakeredis.aioredis import FakeRedis

from backend.app.core import oplog
from backend.app.core.oplog import OPLOG_KEY, OPLOG_MAX


@pytest.fixture
async def fake_redis(monkeypatch):
    r = FakeRedis(decode_responses=True)
    monkeypatch.setattr(oplog, "get_platform_redis", lambda: r)
    return r


async def test_oplog_trimmed_to_1000(fake_redis):
    """PRD §17.1：写入超 1000 条后仅保留最近 1000。"""
    for i in range(OPLOG_MAX + 5):
        await oplog.record(site="s", resource="redis-01", operation="DELETE_KEY", target=f"k{i}")

    r = fake_redis
    assert await r.llen(OPLOG_KEY) == OPLOG_MAX
    newest = await r.lindex(OPLOG_KEY, 0)
    assert f"k{OPLOG_MAX + 4}" in newest  # 最新在前


async def test_read_recent_returns_latest_n(fake_redis):
    for i in range(30):
        await oplog.record(site="s", resource="redis-01", operation="SET_KEY", target=f"k{i}")

    entries = await oplog.read_recent(20)
    assert len(entries) == 20
    assert entries[0]["target"] == "k29"  # 最新
    assert entries[19]["target"] == "k10"  # 最早仍在保留窗内


async def test_read_page(fake_redis):
    for i in range(25):
        await oplog.record(site="s", resource="redis-01", operation="SET_KEY", target=f"k{i}")

    items, total = await oplog.read_page(page=2, size=20)
    assert total == 25
    assert len(items) == 5  # 末页余量
