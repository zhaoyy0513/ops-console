"""Redis 模块服务层：info / SCAN 浏览 / Key 详情 / 受控写操作。

平台 Redis 与业务 Redis 严格隔离（PRD §17.1）：本文件只通过
TargetRedisProvider 访问业务 Redis，平台侧数据一律走 core。
"""

import time
from typing import Any

from backend.app.core.cache import cached
from backend.app.core import oplog
from backend.app.core.config import settings
from backend.app.modules.redis.provider import TargetRedisProvider
from backend.app.modules.sites.service import NotFound
from backend.app.shared import testconn
from backend.app.shared.concurrency import get_semaphore
from backend.app.shared.errors import OpsError
from backend.app.shared.retry import with_retry
from backend.app.shared.timeout import with_timeout

CACHE_TTL = 5  # PRD §14
KEY_TYPES = ("string", "hash", "list", "set", "zset")  # PRD §11.4

# PRD §11.6：以下能力在实现层不可达（非仅前端隐藏）
FORBIDDEN_OPS = {"flushdb", "flushall", "config", "shutdown", "script_flush", "eval"}


def _build_provider(config: dict[str, Any]) -> TargetRedisProvider:
    return TargetRedisProvider(config)


async def _require_redis_config(site_id: str, redis_id: str) -> dict[str, Any]:
    from backend.app.modules.sites import service as sites_service

    config = await sites_service.get_resource_raw(site_id, "redis", redis_id)
    if not config:
        raise NotFound(f"redis instance not found: {redis_id}")
    return config


# ---------- Overview（PRD §11.1） ----------


async def get_info(site_id: str, redis_id: str, db: int | None = None) -> dict[str, Any]:
    config = await _require_redis_config(site_id, redis_id)
    provider = _build_provider(config)

    async def factory():
        async with get_semaphore("target_redis"):
            return await provider.get_info(db)

    return await cached(f"ops:cache:redis:{redis_id}:info", CACHE_TTL, with_retry(factory))


# ---------- SCAN 浏览（PRD §11.2/§11.3） ----------


async def list_keys(
    site_id: str,
    redis_id: str,
    *,
    db: int = 0,
    pattern: str = "*",
    cursor: int = 0,
    count: int = 100,
    key_type: str | None = None,
) -> dict[str, Any]:
    """浏览 Key（PRD §11.2/§11.3），禁 KEYS（验收 9）。

    pattern 含 glob 通配符（*?[）时按 SCAN MATCH 原语义；否则为
    大小写不敏感的模糊子串搜索：服务端渐进 scan + 过滤攒批，
    cursor 分页语义不变（返回 0 表示遍历结束）。

    # ponytail: 模糊模式最多扫 200 轮（200*count 个 key）防止大库长占连接；
    # 有更大库需求再改游标快照
    """
    if key_type is not None and key_type not in KEY_TYPES:
        raise OpsError("INVALID_KEY_TYPE", f"unknown key type: {key_type}", status_code=400)
    config = await _require_redis_config(site_id, redis_id)
    provider = _build_provider(config)

    raw = pattern or "*"
    use_glob = any(ch in raw for ch in "*?[")
    needle = raw.lower() if not use_glob else ""

    async with get_semaphore("target_redis"):
        try:
            async with provider._client(db) as c:
                cur = int(cursor)
                rounds = 0
                collected: list[str] = []
                while True:
                    cur, keys = await with_timeout(
                        c.scan(cursor=cur, match=(raw if use_glob else "*"), count=count),
                        settings_timeout(),
                        resource=config["host"],
                    )
                    if not use_glob and needle:
                        collected.extend(k for k in keys if needle in k.lower())
                    else:
                        collected.extend(keys)
                    rounds += 1
                    if len(collected) >= count or int(cur) == 0 or rounds >= 200:
                        break
                collected = collected[:count]
                # 批量取类型，供列表展示 + 客户端过滤
                types: dict[str, str] = {}
                if collected:
                    async with c.pipeline(transaction=False) as p:
                        for k in collected:
                            p.type(k)
                        results = await p.execute()
                    types = dict(zip(collected, results))
        except OpsError:
            raise
        except (ConnectionError, TimeoutError, OSError) as e:
            raise OpsError("REMOTE_CONNECTION_FAILED", f"Redis query failed: {e}", config["host"]) from None

    items = [{"key": k, "type": types.get(k, "none")} for k in collected]
    if key_type:
        items = [i for i in items if i["type"] == key_type]
    return {"keys": items, "cursor": int(cur), "count": len(items)}


def settings_timeout() -> float:
    from backend.app.core.config import settings

    return float(settings.redis_connect_timeout)


# ---------- Key 详情（PRD §11.4） ----------


async def get_key(site_id: str, redis_id: str, *, db: int = 0, key: str) -> dict[str, Any]:
    config = await _require_redis_config(site_id, redis_id)
    provider = _build_provider(config)

    async with get_semaphore("target_redis"):
        try:
            async with provider._client(db) as c:
                ktype = await c.type(key)
                if ktype == "none":
                    # 明确语义：key 已不存在（删除/过期），而非 HTTP 404 资源缺失
                    raise NotFound("Key 不存在（可能已被删除或已过期）")
                ttl = await c.ttl(key)
                try:
                    memory = await c.memory_usage(key)
                except Exception:  # noqa: BLE001 - 老版本/代理不支持 MEMORY USAGE
                    memory = None
                value = await _read_value(c, key, ktype)
        except OpsError:
            raise
        except (ConnectionError, TimeoutError, OSError) as e:
            raise OpsError("REMOTE_CONNECTION_FAILED", f"Redis query failed: {e}", config["host"]) from None

    return {
        "key": key,
        "type": ktype,
        "ttl": ttl,  # 秒；-1 无过期；-2 不存在
        "memory_usage": memory,
        "value": value,
    }


async def _read_value(c, key: str, ktype: str) -> Any:
    # ponytail: LIST/SET/ZSET 全量读取，超大 key 前端截断展示；V1 不做分片读取
    if ktype == "string":
        return await c.get(key)
    if ktype == "hash":
        return await c.hgetall(key)
    if ktype == "list":
        return await c.lrange(key, 0, -1)
    if ktype == "set":
        return sorted(await c.smembers(key))
    if ktype == "zset":
        return [[score, member] for member, score in await c.zrange(key, 0, -1, withscores=True)]
    return None


# ---------- 受控写操作（PRD §11.4/§11.5/§11.6，唯一可写资源） ----------


def _validate_value(ktype: str, value: Any) -> None:
    """value 结构校验（T18 验收：非法参数 422，不触达 Redis）。"""
    ok = {
        "string": lambda v: isinstance(v, str),
        "hash": lambda v: isinstance(v, dict) and all(isinstance(k, str) for k in v),
        "list": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
        "set": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
        "zset": lambda v: isinstance(v, list)
        and all(isinstance(x, (list, tuple)) and len(x) == 2 for x in v),
    }.get(ktype)
    if ok is None or not ok(value):
        raise OpsError(
            "INVALID_OPERATION",
            f"value structure mismatch for type {ktype}",
            status_code=400,
        )


async def _write_value(c, key: str, ktype: str, value: Any) -> None:
    if ktype == "string":
        await c.set(key, value)
    elif ktype == "hash":
        async with c.pipeline(transaction=True) as p:
            p.delete(key)
            if value:
                p.hset(key, mapping=value)
            await p.execute()
    elif ktype == "list":
        async with c.pipeline(transaction=True) as p:
            p.delete(key)
            if value:
                p.rpush(key, *value)
            await p.execute()
    elif ktype == "set":
        async with c.pipeline(transaction=True) as p:
            p.delete(key)
            if value:
                p.sadd(key, *value)
            await p.execute()
    elif ktype == "zset":
        async with c.pipeline(transaction=True) as p:
            p.delete(key)
            if value:
                p.zadd(key, mapping={str(member): float(score) for score, member in value})
            await p.execute()


async def operate(
    site_id: str,
    redis_id: str,
    *,
    op: str,
    db: int = 0,
    key: str,
    ktype: str | None = None,
    value: Any = None,
    ttl: int | None = None,
) -> dict[str, Any]:
    config = await _require_redis_config(site_id, redis_id)
    started = time.perf_counter()
    # oplog 展示用实例名（配置带 name，见 sites 资源表单）；内部 id 进 params 不进展示列
    instance = str(config.get("name") or redis_id)
    log_params = {"op": op, "db": db, "instance_id": redis_id, "host": config.get("host")}

    if op in FORBIDDEN_OPS:
        raise OpsError("FORBIDDEN_OPERATION", f"operation not allowed: {op}", status_code=400)

    if op == "set":
        if ktype not in KEY_TYPES:
            raise OpsError("INVALID_OPERATION", "set requires a valid key type", status_code=400)
        _validate_value(ktype, value)
        action = "REDIS_SET_KEY"
    elif op == "delete":
        action = "REDIS_DELETE_KEY"
    elif op == "expire":
        if ttl is None:
            raise OpsError("INVALID_OPERATION", "expire requires ttl", status_code=400)
        action = "REDIS_EXPIRE_KEY"
    else:
        raise OpsError("INVALID_OPERATION", f"unknown operation: {op}", status_code=400)

    provider = _build_provider(config)
    async with get_semaphore("target_redis"):
        try:
            async with provider._client(db) as c:
                if op == "set":
                    await _write_value(c, key, ktype, value)
                elif op == "delete":
                    await c.delete(key)
                elif op == "expire":
                    if ttl < 0:
                        await c.persist(key)  # 清除过期（PRD §11.4 可设置/清除）
                    else:
                        await c.expire(key, ttl)
        except OpsError:
            raise
        except (ConnectionError, TimeoutError, OSError) as e:
            await oplog.record(site_id, f"redis/{instance}", action, target=key,
                               params=log_params, result="FAILED", error=str(e))
            raise OpsError("REMOTE_CONNECTION_FAILED", f"Redis write failed: {e}", config["host"]) from None

    # 验收 13：所有修改/删除操作记操作日志。params 不含 value（可能大或敏感）
    await oplog.record(site_id, f"redis/{instance}", action, target=key,
                       params={**log_params, "type": ktype, "ttl": ttl})
    return {"success": True, "latency_ms": int((time.perf_counter() - started) * 1000)}


# ---------- 连接测试（PRD §13） ----------


async def redis_tester(config: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    provider = _build_provider(config)
    async with get_semaphore("target_redis"):
        # 连接测试 5s 硬顶（用户要求：连不上 5 秒就该报失败，不拖满 axios 超时）
        message = await with_timeout(
            provider.run_test(config.get("db")),
            float(settings.redis_connect_timeout),
            resource=config.get("host"),
        )
    return {
        "success": True,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "message": message,
    }


def register_tester() -> None:
    testconn.register_tester("redis", redis_tester)
