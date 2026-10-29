"""Device 模块服务层（PRD §12）：列表/详情 + 连接测试，5s 缓存。"""

import time
from typing import Any

from backend.app.core.cache import cached
from backend.app.modules.device.provider import HttpDeviceProvider, find_missing_fields
from backend.app.modules.sites.service import NotFound
from backend.app.shared import testconn
from backend.app.shared.concurrency import get_semaphore
from backend.app.shared.errors import OpsError
from backend.app.shared.retry import with_retry

CACHE_TTL = 5  # PRD §14


def _build_provider(config: dict[str, Any]) -> HttpDeviceProvider:
    return HttpDeviceProvider(config)


async def _require_device_config(site_id: str, device_id: str) -> dict[str, Any]:
    from backend.app.modules.sites import service as sites_service

    config = await sites_service.get_resource_raw(site_id, "devices", device_id)
    if not config:
        raise NotFound(f"device instance not found: {device_id}")
    return config


async def _instance_payload(
    site_id: str,
    device_id: str,
    config: dict[str, Any] | None = None,
    provider: HttpDeviceProvider | None = None,
) -> dict[str, Any]:
    """一次拉取的完整结果：设备列表 + 耗时 + 字段映射失效（同一份响应，共用缓存）。"""
    config = config or await _require_device_config(site_id, device_id)
    provider = provider or _build_provider(config)

    async def factory():
        async with get_semaphore("device"):
            items = await provider.get_device_list()
        first = items[0] if items else None
        return {
            "items": items,
            "latency_ms": getattr(provider, "last_latency_ms", None),
            "missing_fields": find_missing_fields(
                first.get("_raw") if isinstance(first, dict) else None,
                config.get("field_map"),
                config.get("custom_fields"),
            ),
        }

    return await cached(f"ops:cache:device:{device_id}:status", CACHE_TTL, with_retry(factory))


async def list_devices(site_id: str, device_id: str) -> list[dict[str, Any]]:
    return (await _instance_payload(site_id, device_id))["items"]


async def get_instance_health(site_id: str, device_id: str) -> dict[str, Any]:
    """实例信息条用：响应耗时 + 字段映射失效检测。上游失败也带回耗时（ok=false）。"""
    config = await _require_device_config(site_id, device_id)
    provider = _build_provider(config)
    try:
        payload = await _instance_payload(site_id, device_id, config, provider)
    except OpsError:
        return {"ok": False, "latency_ms": getattr(provider, "last_latency_ms", None), "missing_fields": []}
    return {"ok": True, "latency_ms": payload["latency_ms"], "missing_fields": payload["missing_fields"]}


async def get_device(site_id: str, device_id: str, rid: str) -> dict[str, Any]:
    config = await _require_device_config(site_id, device_id)
    provider = _build_provider(config)

    async def factory():
        async with get_semaphore("device"):
            return await provider.get_device_detail(rid)

    return await cached(f"ops:cache:device:{device_id}:detail:{rid}", CACHE_TTL, with_retry(factory))


async def get_raw_sample(site_id: str, device_id: str) -> dict[str, Any]:
    """取一条原始 JSON 数据（字段映射配置用）。"""
    config = await _require_device_config(site_id, device_id)
    provider = _build_provider(config)

    async def factory():
        async with get_semaphore("device"):
            return await provider.get_raw_sample()

    sample = await with_retry(factory)()
    if not sample:
        raise NotFound("接口未返回任何 Device 数据，无法提取字段")
    return {
        "fields": sorted(sample.keys()),
        "sample": sample,
    }


async def device_tester(config: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    provider = _build_provider(config)
    async with get_semaphore("device"):
        message = await provider.run_test()
    return {
        "success": True,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "message": message,
    }


def register_tester() -> None:
    testconn.register_tester("device", device_tester)


__all__ = ["list_devices", "get_instance_health", "get_device", "device_tester", "register_tester", "OpsError"]
