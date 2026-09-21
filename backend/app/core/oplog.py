import json
from datetime import datetime, timezone

from .redis import get_platform_redis

OPLOG_KEY = "ops:oplog"
OPLOG_MAX = 1000  # PRD §17.1：只保留最近 1000 条


async def record(
    site: str,
    resource: str,
    operation: str,
    *,
    target: str | None = None,
    params: dict | None = None,
    result: str = "SUCCESS",
    error: str | None = None,
) -> None:
    """记录一条操作日志（无用户维度，PRD §17）。

    LPUSH + LTRIM 在同一事务管道内执行，超出 OPLOG_MAX 即淘汰旧日志。
    """
    entry = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "site": site,
        "resource": resource,
        "operation": operation,
        "target": target,
        "params": params,
        "result": result,
        "error": error,
    }
    async with get_platform_redis().pipeline(transaction=True) as pipe:
        pipe.lpush(OPLOG_KEY, json.dumps(entry, ensure_ascii=False))
        pipe.ltrim(OPLOG_KEY, 0, OPLOG_MAX - 1)
        await pipe.execute()


async def read_recent(n: int = 20) -> list[dict]:
    """最近 n 条（新→旧），Overview「最近操作」用。"""
    raw = await get_platform_redis().lrange(OPLOG_KEY, 0, n - 1)
    return [json.loads(x) for x in raw]


async def read_page(page: int = 1, size: int = 50) -> tuple[list[dict], int]:
    """分页读全量（新→旧），返回 (条目, 总数)，操作日志页面用。"""
    r = get_platform_redis()
    total = await r.llen(OPLOG_KEY)
    start = max(0, (page - 1) * size)
    raw = await r.lrange(OPLOG_KEY, start, start + size - 1)
    return [json.loads(x) for x in raw], total
