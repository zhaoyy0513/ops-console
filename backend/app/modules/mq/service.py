"""MQ 模块服务层：overview / queues / addresses + 诊断 + backlog 趋势采样。"""

import time
from typing import Any

from backend.app.core import sampling
from backend.app.core.cache import cached
from backend.app.modules.mq.provider import ArtemisProvider
from backend.app.modules.sites.service import NotFound
from backend.app.shared import testconn
from backend.app.shared.concurrency import get_semaphore
from backend.app.shared.errors import OpsError
from backend.app.shared.retry import with_retry

CACHE_TTL = 5  # PRD §14

# 阈值常量（PRD §9.5 示例：backlog 12381 -> WARNING；未给具体数，先取整档）
# ponytail: 硬编码常量，出现"现场要求可调"再挂进阈值三层体系
BACKLOG_WARNING = 5000
BACKLOG_CRITICAL = 20000
GROWTH_WARNING = 1000  # 5 分钟增长量


def _build_provider(config: dict[str, Any]) -> ArtemisProvider:
    return ArtemisProvider(config)


async def _require_mq_config(site_id: str, mq_id: str) -> dict[str, Any]:
    from backend.app.modules.sites import service as sites_service

    config = await sites_service.get_resource_raw(site_id, "mq", mq_id)
    if not config:
        raise NotFound(f"mq instance not found: {mq_id}")
    return config


async def get_overview(site_id: str, mq_id: str) -> dict[str, Any]:
    config = await _require_mq_config(site_id, mq_id)
    provider = _build_provider(config)

    async def factory():
        async with get_semaphore("mq"):
            return await provider.get_overview()

    return await cached(f"ops:cache:mq:{mq_id}:overview", CACHE_TTL, with_retry(factory))


async def get_queues(site_id: str, mq_id: str) -> list[dict[str, Any]]:
    """队列列表 + 5 分钟趋势 + 逐队列诊断（PRD §9.5/§9.6）。"""
    config = await _require_mq_config(site_id, mq_id)
    provider = _build_provider(config)

    async def factory():
        async with get_semaphore("mq"):
            return await provider.get_queues()

    queues = await cached(f"ops:cache:mq:{mq_id}:queues", CACHE_TTL, with_retry(factory))
    for q in queues:
        name = q.get("name") or ""
        series = _series_key(mq_id, name)
        old = await sampling.value_minutes_ago(series, "backlog", minutes=5)
        current = q.get("message_count")
        if isinstance(current, (int, float)):
            await sampling.push_sample(series, "backlog", current)
        growth = (current - old) if (old is not None and isinstance(current, (int, float))) else None
        q["backlog_5m_ago"] = old
        q["growth_5m"] = growth
        q["diagnosis"] = diagnose_queue(q)
    return queues


def _series_key(mq_id: str, queue_name: str) -> str:
    # queue 名可能含特殊字符，用 hash 化避免 key 结构被污染
    import hashlib

    return f"{mq_id}:{hashlib.md5(queue_name.encode()).hexdigest()[:10]}"


def diagnose_queue(q: dict[str, Any]) -> dict[str, Any]:
    issues = []
    count = q.get("message_count")
    consumers = q.get("consumer_count")
    growth = q.get("growth_5m")
    if isinstance(count, (int, float)):
        if count >= BACKLOG_CRITICAL:
            issues.append({"type": "BACKLOG_HIGH", "severity": "CRITICAL", "value": count,
                           "message": f"Backlog {count}"})
        elif count >= BACKLOG_WARNING:
            issues.append({"type": "BACKLOG_HIGH", "severity": "WARNING", "value": count,
                           "message": f"Backlog {count}"})
    if isinstance(consumers, (int, float)) and consumers == 0 and isinstance(count, (int, float)) and count > 0:
        issues.append({"type": "NO_CONSUMER", "severity": "WARNING", "value": 0,
                       "message": f"{count} messages with no consumer"})
    if isinstance(growth, (int, float)) and growth >= GROWTH_WARNING:
        issues.append({"type": "BACKLOG_GROWING", "severity": "WARNING", "value": growth,
                       "message": f"+{growth} in 5 min"})
    return {"status": ("CRITICAL" if any(i["severity"] == "CRITICAL" for i in issues)
                       else "WARNING" if issues else "HEALTHY"), "issues": issues}


async def get_addresses(site_id: str, mq_id: str) -> list[dict[str, Any]]:
    config = await _require_mq_config(site_id, mq_id)
    provider = _build_provider(config)

    async def factory():
        async with get_semaphore("mq"):
            return await provider.get_addresses()

    return await cached(f"ops:cache:mq:{mq_id}:addresses", CACHE_TTL, with_retry(factory))


# ---------- 连接测试 ----------


async def mq_tester(config: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    provider = _build_provider(config)
    async with get_semaphore("mq"):
        message = await provider.run_test()
    return {
        "success": True,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "message": message,
    }


def register_tester() -> None:
    testconn.register_tester("mq", mq_tester)
