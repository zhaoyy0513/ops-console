import asyncio

import pytest
from fakeredis.aioredis import FakeRedis

from backend.app.core import cache as cache_mod


@pytest.fixture
async def fake_redis(monkeypatch):
    r = FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache_mod, "get_platform_redis", lambda: r)
    return r


async def test_concurrent_misses_hit_downstream_once(fake_redis):
    """PRD §15：并发 10 次未命中请求只产生 1 次下游调用。"""
    calls = 0

    async def factory():
        nonlocal calls
        await asyncio.sleep(0.05)
        calls += 1
        return {"cpu": 92}

    results = await asyncio.gather(
        *(cache_mod.cached("k", 5, factory) for _ in range(10))
    )

    assert calls == 1
    assert results == [{"cpu": 92}] * 10


async def test_cache_hit_skips_factory(fake_redis):
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return {"v": calls}

    first = await cache_mod.cached("k2", 5, factory)
    second = await cache_mod.cached("k2", 5, factory)

    assert calls == 1
    assert first == second == {"v": 1}
