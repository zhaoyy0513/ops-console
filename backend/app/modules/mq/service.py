"""MQ 模块服务层：overview / queues / addresses + 诊断 + backlog 趋势采样。"""

import time
from typing import Any

from backend.app.core import sampling
from backend.app.core.cache import cached
from backend.app.core import oplog
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
            overview = await provider.get_overview()
            # Heap 采样（趋势图数据源）：仅真实读取时记录，缓存命中不重复采样
            heap = overview.get("jvm", {}).get("heap_used")
            if isinstance(heap, (int, float)):
                await sampling.push_sample(f"mq:{site_id}:{mq_id}", "heap", heap)
            return overview

    return await cached(f"ops:cache:mq:{mq_id}:overview", CACHE_TTL, with_retry(factory))


async def get_queues(site_id: str, mq_id: str) -> list[dict[str, Any]]:
    """队列列表 + 5 分钟趋势 + 逐队列诊断（PRD §9.5/§9.6）。

    两个趋势序列：backlog（message_count 瞬时积压）与 added（messages_added 累计）。
    健康队列消费者即时消化，backlog 恒 0、其增量为 0 是真实但无信息量的；
    added 增量（added_1m / added_5m 吞吐）才是"队列是否在跑"的直观指标。
    """
    config = await _require_mq_config(site_id, mq_id)
    provider = _build_provider(config)

    async def factory():
        async with get_semaphore("mq"):
            queues = await provider.get_queues()
            # 富化放进缓存工厂：采样读写在真实拉取时只做一次（~5s 最坏），
            # 缓存命中（3s 轮询）直接复用富化结果，不重复打平台 Redis
            await _enrich_queues(site_id, mq_id, queues)
            return queues

    return await cached(f"ops:cache:mq:{mq_id}:queues", CACHE_TTL, with_retry(factory))


async def _enrich_queues(site_id: str, mq_id: str, queues: list[dict[str, Any]]) -> None:
    """就地补趋势字段（backlog_5m_ago / growth_5m / added_*）+ 逐队列诊断，并记录新样本。"""
    series = {q.get("name") or "": _series_key(site_id, mq_id, q.get("name") or "") for q in queues}
    pairs = [(series[q.get("name") or ""], s) for q in queues for s in ("backlog", "added")]
    olds = await sampling.values_minutes_ago(pairs, minutes=5)  # 先读旧值，再写新样本
    olds_1m = await sampling.values_minutes_ago([(k, "added") for k in series.values()], minutes=1)
    pushes: list[tuple[str, str, float]] = []
    for q in queues:
        key = series[q.get("name") or ""]
        backlog, added = q.get("message_count"), q.get("messages_added")
        if isinstance(backlog, (int, float)):
            pushes.append((key, "backlog", backlog))
        if isinstance(added, (int, float)):
            pushes.append((key, "added", added))
        old_backlog, old_added = olds.get((key, "backlog")), olds.get((key, "added"))
        old_added_1m = olds_1m.get((key, "added"))
        q["backlog_5m_ago"] = old_backlog
        q["growth_5m"] = (backlog - old_backlog) if (old_backlog is not None and isinstance(backlog, (int, float))) else None
        # added 为负只可能是 broker 重启计数清零，截断为 0；added_1m 无 1 分钟历史时 None（预热）
        q["added_5m"] = max(added - old_added, 0) if (old_added is not None and isinstance(added, (int, float))) else None
        q["added_1m"] = max(added - old_added_1m, 0) if (old_added_1m is not None and isinstance(added, (int, float))) else None
        q["diagnosis"] = diagnose_queue(q)
    await sampling.push_samples(pushes)


def _series_key(site_id: str, mq_id: str, queue_name: str) -> str:
    # queue 名可能含特殊字符，用 hash 化避免 key 结构被污染；带站点维度防跨站同名
    import hashlib

    return f"mq:{site_id}:{mq_id}:{hashlib.md5(queue_name.encode()).hexdigest()[:10]}"


def diagnose_queue(q: dict[str, Any]) -> dict[str, Any]:
    issues = []
    count = q.get("message_count")
    consumers = q.get("consumer_count")
    growth = q.get("growth_5m")
    if isinstance(count, (int, float)):
        if count >= BACKLOG_CRITICAL:
            issues.append({"type": "BACKLOG_HIGH", "severity": "CRITICAL", "value": count,
                           "message": f"积压 {count} 条消息"})
        elif count >= BACKLOG_WARNING:
            issues.append({"type": "BACKLOG_HIGH", "severity": "WARNING", "value": count,
                           "message": f"积压 {count} 条消息"})
    if isinstance(consumers, (int, float)) and consumers == 0 and isinstance(count, (int, float)) and count > 0:
        issues.append({"type": "NO_CONSUMER", "severity": "WARNING", "value": 0,
                       "message": f"有 {count} 条消息但没有任何消费者"})
    if isinstance(growth, (int, float)) and growth >= GROWTH_WARNING:
        issues.append({"type": "BACKLOG_GROWING", "severity": "WARNING", "value": growth,
                       "message": f"5 分钟内增长 {growth} 条"})
    return {"status": ("CRITICAL" if any(i["severity"] == "CRITICAL" for i in issues)
                       else "WARNING" if issues else "HEALTHY"), "issues": issues}


async def get_addresses(site_id: str, mq_id: str) -> list[dict[str, Any]]:
    config = await _require_mq_config(site_id, mq_id)
    provider = _build_provider(config)

    async def factory():
        async with get_semaphore("mq"):
            return await provider.get_addresses()

    return await cached(f"ops:cache:mq:{mq_id}:addresses", CACHE_TTL, with_retry(factory))


def _validate_queue_mbean(mbean: str) -> None:
    """mbean 必须形如队列 ObjectName（来自本平台队列列表），防任意 MBean 调用。"""
    if "component=addresses" not in mbean or "subcomponent=queues" not in mbean \
            or mbean.count('"') % 2 != 0 or any(c in mbean for c in "\r\n{}"):
        raise OpsError("INVALID_OPERATION", "invalid queue mbean", status_code=400)


async def empty_queue(site_id: str, mq_id: str, mbean: str, queue_name: str) -> dict[str, Any]:
    """清空指定队列的积压消息（用户要求的管理操作；写 oplog）。"""
    config = await _require_mq_config(site_id, mq_id)
    _validate_queue_mbean(mbean)
    provider = _build_provider(config)
    started = time.perf_counter()
    # oplog 可读性：resource 用实例名（内部 id 移入 params，oplog.record docstring 约定）
    res = f"mq/{config.get('name') or mq_id}"
    extra = {"op": "removeMessages", "instance_id": mq_id, "host": config.get("host")}
    async with get_semaphore("mq"):
        try:
            removed = await provider.empty_queue(mbean)
        except OpsError as e:
            await oplog.record(site_id, res, "MQ_EMPTY_QUEUE", target=queue_name,
                               params=extra, result="FAILED", error=e.message)
            raise
    await oplog.record(site_id, res, "MQ_EMPTY_QUEUE", target=queue_name,
                       params=extra)
    return {"success": True, "removed": removed, "latency_ms": int((time.perf_counter() - started) * 1000)}


async def browse_queue(site_id: str, mq_id: str, mbean: str, queue_name: str,
                       limit: int = 20) -> list[dict[str, Any]]:
    """浏览队列内消息（只读预览，前 limit 条）。"""
    config = await _require_mq_config(site_id, mq_id)
    _validate_queue_mbean(mbean)
    provider = _build_provider(config)
    async with get_semaphore("mq"):
        return await provider.browse_queue(mbean, limit)


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
