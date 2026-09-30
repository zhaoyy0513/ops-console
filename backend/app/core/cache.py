import asyncio
import json

from backend.app.shared.errors import OpsError

from .redis import get_platform_redis

_ERROR_FIELD = "__ops_error__"


def _unwrap(raw: str):
    """缓存值 json -> 结果；命中错误哨兵（负缓存）即抛 OpsError，不再出网。"""
    value = json.loads(raw)
    if isinstance(value, dict) and _ERROR_FIELD in value:
        raise OpsError("REMOTE_CONNECTION_FAILED", value[_ERROR_FIELD])
    return value


async def cached(key: str, ttl: int, factory):
    """短 TTL 缓存 + 单飞锁（PRD §14/§15 请求合并）。

    命中缓存直接返回；未命中时抢到锁的协程执行 factory() 并写缓存，
    其余协程等待缓存写入后读取，避免并发重复查询外部系统。
    factory 失败时向同 key 写错误哨兵（同 TTL 负缓存）：死资源每个 TTL
    至多一次出网尝试，重连风暴由哨兵挡住，首调用方收到原始异常。
    """
    r = get_platform_redis()
    raw = await r.get(key)
    if raw is not None:
        return _unwrap(raw)

    lock_key = f"lock:{key}"
    if await r.set(lock_key, "1", nx=True, ex=ttl):
        try:
            try:
                value = await factory()
            except Exception as e:  # noqa: BLE001 - 失败也按 TTL 记住（负缓存）
                await r.set(key, json.dumps({_ERROR_FIELD: str(e)[:120]}), ex=ttl)
                raise
            await r.set(key, json.dumps(value), ex=ttl)
            return value
        finally:
            await r.delete(lock_key)

    # 锁被他人持有：等对方写缓存（最多约 2s），超时则自己查
    for _ in range(20):
        await asyncio.sleep(0.1)
        raw = await r.get(key)
        if raw is not None:
            return _unwrap(raw)
    return await factory()
