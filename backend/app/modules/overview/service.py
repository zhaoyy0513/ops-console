"""Overview 模块服务层：后台健康检查 + 站点聚合视图（PRD §7/§16）。"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any

from backend.app.core import events, oplog
from backend.app.core.redis import get_platform_redis
from backend.app.shared.concurrency import get_semaphore


def health_key(site_id: str) -> str:
    return f"ops:health:{site_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def check_site(site_id: str) -> int:
    """单站点全资源轻量检查，结果写平台 Redis hash。返回检查项数。

    站点内逐资源串行；每次出网调用都过资源类型信号量，健康检查与
    前台查询共享并发上限，避免 30s 批量检查挤占正常请求。
    """
    from backend.app.modules.device.provider import HttpDeviceProvider
    from backend.app.modules.mq.provider import ArtemisProvider
    from backend.app.modules.redis.provider import TargetRedisProvider
    from backend.app.modules.server.provider import SSHServerMetricsProvider
    from backend.app.modules.sites import service as sites_service

    entries: dict[str, str] = {}

    async def put(field: str, name: str, coro_factory, sem_type: str) -> None:
        try:
            async with get_semaphore(sem_type):
                result = await coro_factory()
        except Exception as e:  # noqa: BLE001 - 检查失败即 CRITICAL（不可达本身是异常）
            result = {"status": "CRITICAL", "message": str(e)[:120]}
        entries[field] = json.dumps(
            {"name": name, "checked_at": _now(), **result}, ensure_ascii=False
        )

    for cfg in await sites_service.list_resources(site_id, "servers", include_password=True):
        if not cfg.get("enabled", True):
            continue
        provider = SSHServerMetricsProvider(cfg)
        # CPU/内存趋势采样在 server 模块真实读取时记录（前端 5s 轮询驱动）
        await put(f"server:{cfg['id']}", cfg["name"], provider.health_check, "ssh")

    for cfg in await sites_service.list_resources(site_id, "redis", include_password=True):
        if not cfg.get("enabled", True):
            continue
        provider = TargetRedisProvider(cfg)

        async def redis_check(provider=provider):
            message = await provider.run_test()
            return {"status": "HEALTHY", "message": message}

        await put(f"redis:{cfg['id']}", cfg["name"], redis_check, "target_redis")

    for cfg in await sites_service.list_resources(site_id, "mq", include_password=True):
        if not cfg.get("enabled", True):
            continue
        provider = ArtemisProvider(cfg)

        async def mq_check(provider=provider):
            overview = await provider.get_overview()
            status = "HEALTHY" if overview.get("status") == "STARTED" else "WARNING"
            return {"status": status, "message": f"{overview.get('status')} {overview.get('version')}"}

        await put(f"mq:{cfg['id']}", cfg["name"], mq_check, "mq")

    for cfg in await sites_service.list_resources(site_id, "devices", include_password=True):
        if not cfg.get("enabled", True):
            continue
        provider = HttpDeviceProvider(cfg)

        async def device_check(provider=provider):
            message = await provider.run_test()
            return {"status": "HEALTHY", "message": message}

        await put(f"device:{cfg['id']}", cfg["name"], device_check, "device")

    if entries:
        r = get_platform_redis()
        # 上一轮结果必须在覆盖前读走：状态跳变（进入/恢复 CRITICAL）靠它判定，
        # 同一 CRITICAL 持续 30s 重查不会重复记事件（边沿触发即去重）。
        prev_raw = await r.hgetall(health_key(site_id))
        prev: dict[str, dict] = {}
        for field, payload in prev_raw.items():
            try:
                prev[field] = json.loads(payload)
            except (TypeError, ValueError):
                pass
        await r.delete(health_key(site_id))
        await r.hset(health_key(site_id), mapping=entries)
        await _record_transitions(site_id, prev, entries)
    return len(entries)


async def _record_transitions(site_id: str, prev: dict[str, dict], entries: dict[str, str]) -> None:
    """诊断状态跳变 → diag 事件（首次检查无旧值，不记）。"""
    for field, payload in entries.items():
        old = prev.get(field)
        if not old:
            continue
        cur = json.loads(payload)
        old_status, new_status = old.get("status"), cur.get("status")
        if old_status == new_status:
            continue
        if new_status == "CRITICAL" and old_status != "CRITICAL":
            title = f"{cur.get('name') or field}: {old_status} → CRITICAL"
        elif old_status == "CRITICAL" and new_status != "CRITICAL":
            title = f"{cur.get('name') or field}: CRITICAL → {new_status}"
        else:
            continue
        await events.record_event(
            site_id, "diag", title, detail=f"{field} {cur.get('message', '')}".strip()
        )


async def check_all_sites() -> None:
    from backend.app.modules.sites import service as sites_service

    sites = [s for s in await sites_service.list_sites() if s.get("enabled", True)]
    # 多站点并发检查；return_exceptions 保证单站点失败不影响其余（hash 仍逐站点各自写）
    await asyncio.gather(*(check_site(s["id"]) for s in sites), return_exceptions=True)


async def get_overview(site_id: str) -> dict[str, Any]:
    """聚合视图（PRD §7）：各类型计数 + 异常摘要 + 最近 20 操作。"""
    from backend.app.modules.sites import service as sites_service

    site = await sites_service.get_site(site_id)
    if not site:
        from backend.app.modules.sites.service import NotFound

        raise NotFound(f"site not found: {site_id}")

    raw = await get_platform_redis().hgetall(health_key(site_id))
    items: list[dict[str, Any]] = []
    for field, payload in raw.items():
        kind, _, rid = field.partition(":")
        entry = json.loads(payload)
        entry.update({"kind": kind, "id": rid})
        items.append(entry)

    types = ("server", "redis", "mq", "device")
    summary: dict[str, dict[str, int]] = {}
    for t in types:
        subset = [i for i in items if i["kind"] == t]
        summary[t] = {
            "total": len(subset),
            "healthy": sum(1 for i in subset if i["status"] == "HEALTHY"),
            "warning": sum(1 for i in subset if i["status"] == "WARNING"),
            "critical": sum(1 for i in subset if i["status"] == "CRITICAL"),
            "unknown": sum(1 for i in subset if i["status"] not in ("HEALTHY", "WARNING", "CRITICAL")),
        }

    order = {"CRITICAL": 3, "WARNING": 2, "UNKNOWN": 1}
    overall = "HEALTHY"
    for i in items:
        if order.get(i["status"], 0) > order.get(overall, 0):
            overall = i["status"]

    issues = sorted(
        (i for i in items if i["status"] != "HEALTHY"),
        key=lambda i: -order.get(i["status"], 0),
    )
    return {
        "site": site,
        "overall": overall,
        "summary": summary,
        "issues": issues,
        "recent_ops": await oplog.read_recent(20),
        "checked_at": max((i["checked_at"] for i in items), default=None),
    }


# ---------- 配置卫生清单（P1）：纯静态判定，零采集 ----------


def hygiene_issues(site: dict, resources: dict[str, list[dict]]) -> list[dict[str, Any]]:
    """按站点/资源配置静态判定卫生问题。纯函数（不 IO），便于直接构造数据测试。

    detail 仅作前端 i18n 缺失时的兜底文案；正常展示按 type 走 i18n。
    """
    issues: list[dict[str, Any]] = []

    def add(kind: str, severity: str, rtype: str, cfg: dict, detail: str) -> None:
        issues.append({
            "type": kind,
            "severity": severity,
            "resource_type": rtype,
            "resource_name": str(cfg.get("name") or cfg.get("id") or ""),
            "detail": detail,
        })

    def enabled(cfgs: list[dict]) -> list[dict]:
        return [c for c in cfgs if c.get("enabled", True)]

    # 站点无阈值时，未覆盖阈值的 Server 全部吃全局默认——提示但不告警
    if not site.get("thresholds"):
        for cfg in enabled(resources.get("servers", [])):
            if not cfg.get("thresholds"):
                add("server_no_thresholds", "info", "server", cfg,
                    "no thresholds on resource or site; global defaults apply")

    for cfg in enabled(resources.get("devices", [])):
        if not cfg.get("field_map") and not cfg.get("custom_fields"):
            add("device_no_field_map", "info", "device", cfg,
                "no field mapping or custom fields configured")

    for rtype in ("redis", "mq"):
        for cfg in enabled(resources.get(rtype, [])):
            if not cfg.get("password"):
                add(f"{rtype}_no_password", "warning", rtype, cfg, "password is empty")

    for cfg in enabled(resources.get("pages", [])):
        if not cfg.get("url") and not cfg.get("html"):
            add("page_empty", "warning", "page", cfg, "neither url nor html configured")

    # 警告在前（前端按返回顺序渲染）
    issues.sort(key=lambda i: i["severity"] != "warning")
    return issues


async def get_hygiene(site_id: str) -> list[dict[str, Any]]:
    from backend.app.modules.sites import service as sites_service

    site = await sites_service.get_site(site_id)
    if not site:
        from backend.app.modules.sites.service import NotFound

        raise NotFound(f"site not found: {site_id}")
    resources = {
        t: await sites_service.list_resources(site_id, t, include_password=True)
        for t in ("servers", "devices", "redis", "mq", "pages")
    }
    return hygiene_issues(site, resources)


async def get_events(site_id: str, limit: int = 50) -> list[dict[str, Any]]:
    from backend.app.modules.sites import service as sites_service

    if not await sites_service.get_site(site_id):
        from backend.app.modules.sites.service import NotFound

        raise NotFound(f"site not found: {site_id}")
    return await events.read_events(site_id, limit)
