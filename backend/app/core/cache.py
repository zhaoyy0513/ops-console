import asyncio
import json

from .redis import get_platform_redis


async def cached(key: str, ttl: int, factory):
    """短 TTL 缓存 + 单飞锁（PRD §14/§15 请求合并）。

    命中缓存直接返回；未命中时抢到锁的协程执行 factory() 并写缓存，
    其余协程等待缓存写入后读取，避免并发重复查询外部系统。

    # ponytail: factory 失败时等待方会各自重查一次，失败风暴由
    # shared/concurrency 信号量兜底，这里不做额外抑制
    """
    r = get_platform_redis()
    raw = await r.get(key)
    if raw is not None:
        return json.loads(raw)

    lock_key = f"lock:{key}"
    if await r.set(lock_key, "1", nx=True, ex=ttl):
        try:
            value = await factory()
            await r.set(key, json.dumps(value), ex=ttl)
            return value
        finally:
            await r.delete(lock_key)

    # 锁被他人持有：等对方写缓存（最多约 2s），超时则自己查
    for _ in range(20):
        await asyncio.sleep(0.1)
        raw = await r.get(key)
        if raw is not None:
            return json.loads(raw)
    return await factory()
