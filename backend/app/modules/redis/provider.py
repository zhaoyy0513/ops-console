"""被监控 Redis 的 Provider（PRD §11）。

业务 Redis 是"监控对象"，连接由本模块按站点配置动态创建、查完即关；
与平台 Redis（core/redis.py，OPS_REDIS_URL）是不同连接对象，严禁混用。
"""

from typing import Any

import redis.asyncio as aioredis

from backend.app.core.config import settings
from backend.app.shared.errors import OpsError
from backend.app.shared.timeout import with_timeout


def _int(info: dict[str, Any], key: str) -> int | None:
    """INFO 字段取整数；缺失/解析失败 -> None（不造默认 0）。"""
    v = info.get(key)
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float(info: dict[str, Any], key: str) -> float | None:
    v = info.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _str(info: dict[str, Any], key: str) -> str | None:
    v = info.get(key)
    return v if isinstance(v, str) else None


def normalize_info(info: dict[str, Any]) -> dict[str, Any]:
    """INFO 原始字典 -> PRD §11.1 字段（纯函数，独立可测）。

    每个字段独立容错：缺失或解析异常只让该字段为 None，不影响其它字段。
    """
    hits = _int(info, "keyspace_hits")
    misses = _int(info, "keyspace_misses")
    # 命中率需要两个计数都拿到才可信；分母为 0 时无意义 -> None
    total_lookups = hits + misses if hits is not None and misses is not None else 0
    hit_rate = round(hits / total_lookups * 100, 1) if total_lookups else None
    # 各 DB 的 key 数：redis-py 把 keyspace 段以顶层 dbN 键返回（dbN={keys:105,...}）
    db_sizes = {}
    for k, v in info.items():
        if k.startswith("db") and k[2:].isdigit() and isinstance(v, dict):
            db_sizes[int(k[2:])] = _int(v, "keys")
    db_size = _int(info, "dbsize")
    if db_size is None:
        db_size = _int(info, "db_size")
    return {
        "status": "ok",  # 能拿到 INFO 即在线；失败走 OpsError
        "version": _str(info, "redis_version"),
        "role": _str(info, "role"),
        "uptime_seconds": _int(info, "uptime_in_seconds"),
        "memory_used": _int(info, "used_memory"),
        "memory_peak": _int(info, "used_memory_peak"),
        "memory_max": _int(info, "maxmemory"),  # 0 = 未设上限
        "memory_fragmentation": _float(info, "mem_fragmentation_ratio"),
        "connected_clients": _int(info, "connected_clients"),
        "blocked_clients": _int(info, "blocked_clients"),
        "rejected_connections": _int(info, "rejected_connections"),
        "commands_per_sec": None,  # 采样任务填充（T22 同思路），V1 先给 None
        "ops_per_sec": _int(info, "instantaneous_ops_per_sec"),
        "total_commands_processed": _int(info, "total_commands_processed"),
        "keyspace_hits": hits,
        "keyspace_misses": misses,
        "hit_rate": hit_rate,
        "evicted_keys": _int(info, "evicted_keys"),
        "expired_keys": _int(info, "expired_keys"),
        "rdb_last_bgsave_status": _str(info, "rdb_last_bgsave_status"),
        "aof_last_bgrewrite_status": _str(info, "aof_last_bgrewrite_status"),
        "latest_fork_usec": _int(info, "latest_fork_usec"),
        "db_size": db_size,
        "db_sizes": db_sizes,
    }


class TargetRedisProvider:
    def __init__(self, config: dict[str, Any]):
        self._host: str = config["host"]
        self._port: int = int(config.get("port") or 6379)
        self._username: str = config.get("username") or ""
        self._password: str = config.get("password") or ""
        self._db: int = int(config.get("db") or 0)

    def _client(self, db: int | None = None):
        # 每次调用新建连接（on-demand，Decision 004 同思路）；decode_responses 统一拿 str
        return aioredis.Redis(
            host=self._host,
            port=self._port,
            username=self._username or None,
            password=self._password or None,
            db=self._db if db is None else db,
            decode_responses=True,
            socket_connect_timeout=settings.redis_connect_timeout,
            socket_timeout=settings.redis_connect_timeout,
        )

    async def get_info(self, db: int | None = None) -> dict[str, Any]:
        """Overview（PRD §11.1 字段），来自 INFO。"""
        try:
            async with self._client(db) as c:
                info = await with_timeout(c.info(), settings.redis_connect_timeout, resource=self._host)
                try:
                    info["dbsize"] = await c.dbsize()  # INFO 默认段不含各 DB keyspace
                except Exception:  # noqa: BLE001
                    pass
        except OpsError:
            raise
        except (aioredis.RedisError, OSError) as e:
            raise OpsError("REMOTE_CONNECTION_FAILED", f"Redis connect failed: {e}", self._host) from None
        return normalize_info(info)

    async def run_test(self, db: int | None = None) -> str:
        """连通性测试（PRD §13.2）：连接 + 认证（PING）+ INFO 版本。"""
        try:
            async with self._client(db) as c:
                await c.ping()
                info = await c.info("server")
        except (aioredis.RedisError, OSError) as e:
            raise OpsError("REMOTE_CONNECTION_FAILED", f"Redis connect failed: {e}", self._host) from None
        return f"Connected, Redis {info.get('redis_version', '?')}"
