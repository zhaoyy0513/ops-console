"""负缓存：factory 失败写错误哨兵（同 TTL），TTL 内重试不再出网（重连风暴防护）。"""
import json

import pytest

from backend.app.core import cache as cache_mod
from backend.app.shared.errors import OpsError


async def test_factory_failure_negatively_cached(fake_platform_redis):
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        raise RuntimeError("connection refused (10.5s)")

    # 第一次：factory 真实执行，原始异常透传
    with pytest.raises(RuntimeError):
        await cache_mod.cached("dead", 5, factory)
    assert calls == 1

    # 哨兵已写入同一缓存 key
    raw = await fake_platform_redis.get("dead")
    assert json.loads(raw)["__ops_error__"] == "connection refused (10.5s)"

    # 第二次：哨兵命中立即抛 OpsError，factory 不再被调用
    with pytest.raises(OpsError) as ei:
        await cache_mod.cached("dead", 5, factory)
    assert "connection refused" in ei.value.message
    assert calls == 1  # 出网次数停在 1


async def test_success_overwrites_stale_sentinel(fake_platform_redis):
    """恢复后正常值覆盖哨兵（或普通值不受哨兵逻辑影响）。"""
    async def factory():
        return {"cpu": 92}

    assert await cache_mod.cached("ok", 5, factory) == {"cpu": 92}
    assert await cache_mod.cached("ok", 5, factory) == {"cpu": 92}
