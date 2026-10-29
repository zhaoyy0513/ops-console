"""站点事件流（P1）：诊断状态变化等事件，平台 Redis list，每站点上限 200 条。"""

import json
from datetime import datetime, timezone

import loguru

from .redis import get_platform_redis

EVENTS_MAX = 200


def events_key(site_id: str) -> str:
    return f"ops:events:{site_id}"


async def record_event(site_id: str, kind: str, title: str, detail: str = "") -> None:
    """记一条事件（kind ∈ diag / restart / config / net）。

    fire-and-forget：任何写入失败只记日志，绝不影响调用方主流程。
    """
    try:
        entry = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "title": title,
            "detail": detail,
        }
        async with get_platform_redis().pipeline(transaction=True) as pipe:
            pipe.lpush(events_key(site_id), json.dumps(entry, ensure_ascii=False))
            pipe.ltrim(events_key(site_id), 0, EVENTS_MAX - 1)
            await pipe.execute()
    except Exception as e:  # noqa: BLE001 - 事件是旁路，不得拖垮主流程
        loguru.logger.warning(f"record_event failed (site={site_id}): {e}")


async def read_events(site_id: str, limit: int = 50) -> list[dict]:
    """最近 limit 条（新→旧）。"""
    limit = max(0, min(limit, EVENTS_MAX))
    if limit == 0:
        return []
    raw = await get_platform_redis().lrange(events_key(site_id), 0, limit - 1)
    return [json.loads(x) for x in raw]
