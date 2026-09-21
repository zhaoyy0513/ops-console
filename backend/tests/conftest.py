import pytest
from fakeredis.aioredis import FakeRedis


@pytest.fixture
async def fake_platform_redis(monkeypatch):
    """用 fakeredis 顶替平台 Redis 单例，所有调用方（cache/oplog/各模块）自动生效。"""
    r = FakeRedis(decode_responses=True)
    monkeypatch.setattr("backend.app.core.redis._client", r)
    return r
