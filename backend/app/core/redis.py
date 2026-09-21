import redis.asyncio as redis

from .config import settings

_client: redis.Redis | None = None


def get_platform_redis() -> redis.Redis:
    """平台 Redis 单例：配置存储、缓存、锁、操作日志专用（PRD §17.1）。

    业务 Redis（被监控对象）由 redis 模块的 provider 按站点配置另建连接，
    严禁共用本客户端。
    """
    global _client
    if _client is None:
        _client = redis.from_url(
            settings.ops_redis_url,
            socket_connect_timeout=settings.redis_connect_timeout,
            socket_timeout=settings.redis_connect_timeout,
            decode_responses=True,
        )
    return _client
