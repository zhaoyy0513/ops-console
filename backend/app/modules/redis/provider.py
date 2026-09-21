"""被监控 Redis 的 Provider（PRD §11）。

业务 Redis 是"监控对象"，连接由本模块按站点配置动态创建、查完即关；
与平台 Redis（core/redis.py，OPS_REDIS_URL）是不同连接对象，严禁混用。
"""

from typing import Any

import redis.asyncio as aioredis

from backend.app.core.config import settings
from backend.app.shared.errors import OpsError
from backend.app.shared.timeout import with_timeout


def normalize_info(info: dict[str, Any]) -> dict[str, Any]:
    """INFO 原始字典 -> PRD §11.1 字段（纯函数，独立可测）。"""
    hits = int(info.get("keyspace_hits", 0) or 0)
    misses = int(info.get("keyspace_misses", 0) or 0)
    hit_rate = round(hits / (hits + misses) * 100, 1) if (hits + misses) else None
    return {
        "status": "ok",  # 能拿到 INFO 即在线；失败走 OpsError
        "version": info.get("redis_version"),
        "uptime_seconds": int(info.get("uptime_in_seconds", 0) or 0),
        "memory_used": int(info.get("used_memory", 0) or 0),
        "memory_peak": int(info.get("used_memory_peak", 0) or 0),
        "memory_fragmentation": info.get("mem_fragmentation_ratio"),
        "connected_clients": int(info.get("connected_clients", 0) or 0),
        "commands_per_sec": None,  # 采样任务填充（T22 同思路），V1 先给 None
        "total_commands_processed": int(info.get("total_commands_processed", 0) or 0),
        "hit_rate": hit_rate,
        "evicted_keys": int(info.get("evicted_keys", 0) or 0),
        "expired_keys": int(info.get("expired_keys", 0) or 0),
        "db_size": int(info.get("dbsize", info.get("db_size", 0)) or 0),
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
