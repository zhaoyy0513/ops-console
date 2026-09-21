import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    # 平台 Redis（配置 + 缓存 + 锁 + oplog），与业务 Redis 严格隔离（PRD §6.1/§17.1）
    ops_redis_url: str = os.environ.get("OPS_REDIS_URL", "redis://localhost:6379/5")
    log_level: str = os.environ.get("OPS_LOG_LEVEL", "INFO")

    # 外部系统超时（秒），PRD §25.3 / §26
    ssh_connect_timeout: int = _env_int("SSH_CONNECT_TIMEOUT", 5)
    ssh_command_timeout: int = _env_int("SSH_COMMAND_TIMEOUT", 10)
    http_connect_timeout: int = _env_int("HTTP_CONNECT_TIMEOUT", 5)
    http_read_timeout: int = _env_int("HTTP_READ_TIMEOUT", 10)
    redis_connect_timeout: int = _env_int("REDIS_CONNECT_TIMEOUT", 5)
    mq_api_timeout: int = _env_int("MQ_API_TIMEOUT", 10)


settings = Settings()
