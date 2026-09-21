"""Server 模块服务层：provider 构建、缓存合并、连接测试。"""

import time
from typing import Any

from backend.app.core.cache import cached
from backend.app.modules.server.provider import SSHServerMetricsProvider
from backend.app.modules.sites.service import NotFound
from backend.app.shared import testconn
from backend.app.shared.retry import with_retry
from backend.app.shared.concurrency import get_semaphore

CACHE_TTL = 5  # PRD §14：Server Metrics TTL 5~10s


def _build_provider(config: dict[str, Any]) -> SSHServerMetricsProvider:
    return SSHServerMetricsProvider(config)


async def _require_server_config(site_id: str, server_id: str) -> dict[str, Any]:
    from backend.app.modules.sites import service as sites_service

    # raw：provider 建连需要真实密码（对 API 输出的那份才做脱敏）
    config = await sites_service.get_resource_raw(site_id, "servers", server_id)
    if not config:
        raise NotFound(f"server not found: {server_id}")
    return config


async def _with_cache(site_id: str, server_id: str, kind: str, factory) -> Any:
    async with get_semaphore("ssh"):
        # 读路径套连接级有限重试（PRD §26）；写路径无此资源
        return await cached(f"ops:cache:server:{server_id}:{kind}", CACHE_TTL, with_retry(factory))


async def get_metrics(site_id: str, server_id: str) -> dict[str, Any]:
    from backend.app.modules.server.diagnosis import diagnose, merge_thresholds
    from backend.app.modules.sites import service as sites_service

    config = await _require_server_config(site_id, server_id)
    site = await sites_service.get_site(site_id)

    def factory():
        provider = _build_provider(config)
        return provider.get_metrics()

    metrics = await _with_cache(site_id, server_id, "metrics", factory)
    # 诊断不走缓存值缓存，但用同一份 metrics 计算，零额外 SSH
    thresholds = merge_thresholds(config.get("thresholds"), (site or {}).get("thresholds"))
    return {**metrics, "diagnosis": diagnose(metrics, thresholds)}


async def get_processes(site_id: str, server_id: str) -> list[dict[str, Any]]:
    config = await _require_server_config(site_id, server_id)
    provider = _build_provider(config)
    return await _with_cache(site_id, server_id, "processes", provider.get_processes)


async def server_tester(config: dict[str, Any]) -> dict[str, Any]:
    """连接测试（PRD §13.2）：连接 + 认证 + 白名单命令可执行。"""
    started = time.perf_counter()
    provider = _build_provider(config)
    async with get_semaphore("ssh"):
        message = await provider.run_test()
    return {
        "success": True,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "message": message,
    }


def register_tester() -> None:
    testconn.register_tester("server", server_tester)
