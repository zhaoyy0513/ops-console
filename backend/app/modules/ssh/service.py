"""SSH 脚本模块：绑定 Server 的脚本管理、手动执行与 cron 定时调度（站点级）。

脚本存储：ops:site:{site_id}:ssh_scripts Hash（id -> JSON）。
扩展字段：cron（非空=定时脚本，标准 5 段 cronie 格式）、sched_enabled
（定时开关）。手动脚本（cron 为空）无启用语义。

调度取舍（设计决策）：用平台内 APScheduler 而非系统 crontab——
①不修改系统 crontab 无残留；②脚本删除/禁用即自动停；
③执行结果与 oplog 天然归平台；④后端启动时从配置自动恢复调度。
缺点：后端宕机期间定时任务暂停（平台为诊断工具定位，可接受）。
"""

import json
import uuid
from typing import Any

import asyncssh

from backend.app.core import oplog
from backend.app.core.config import settings
from backend.app.modules.sites.service import NotFound
from backend.app.modules.sites.service import get_resource_raw
from backend.app.core.redis import get_platform_redis

SCRIPTS_KEY = "ops:site:{site_id}:ssh_scripts"
RUN_TIMEOUT = 60


def _key(site_id: str) -> str:
    return SCRIPTS_KEY.format(site_id=site_id)


async def list_scripts(site_id: str) -> list[dict[str, Any]]:
    await _require_site(site_id)
    raw = await get_platform_redis().hvals(_key(site_id))
    items = [json.loads(x) for x in raw]
    return sorted(items, key=lambda s: (not s.get("cron"), s["name"]))


async def get_script(site_id: str, script_id: str) -> dict[str, Any] | None:
    await _require_site(site_id)
    raw = await get_platform_redis().hget(_key(site_id), script_id)
    return json.loads(raw) if raw else None


async def create_script(site_id: str, data: dict[str, Any]) -> dict[str, Any]:
    await _require_site(site_id)
    r = get_platform_redis()
    script_id = data.get("id") or uuid.uuid4().hex[:8]
    if await r.hexists(_key(site_id), script_id):
        raise ValueError(f"script already exists: {script_id}")
    # 新建的定时脚本强制不启用（保存不执行，表格 switch 打开才开始）
    data = {**data, "id": script_id, "sched_enabled": False}
    await r.hset(_key(site_id), script_id, json.dumps(data, ensure_ascii=False))
    return data


async def update_script(site_id: str, script_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    await _require_site(site_id)
    r = get_platform_redis()
    old = await r.hget(_key(site_id), script_id)
    if not old:
        return None
    merged = {**json.loads(old), **data, "id": script_id}
    await r.hset(_key(site_id), script_id, json.dumps(merged, ensure_ascii=False))
    return merged


async def delete_script(site_id: str, script_id: str) -> bool:
    await _require_site(site_id)
    deleted = await get_platform_redis().hdel(_key(site_id), script_id)
    return deleted > 0


async def _require_site(site_id: str) -> None:
    if not await get_platform_redis().hexists(f"ops:site:{site_id}", "id"):
        raise NotFound(f"site not found: {site_id}")


async def _execute(server_cfg: dict[str, Any], content: str, *,
                     site_id: str, log_resource: str, log_target: str,
                     triggered: str) -> dict[str, Any]:
    """在指定 Server 上执行脚本内容（共享执行体：按 id 执行与 adhoc 测试共用）。"""
    import asyncio
    import time

    started = time.perf_counter()
    timed_out = False
    stdout = ""
    stderr = ""
    try:
        async with asyncssh.connect(
            server_cfg["host"],
            port=int(server_cfg.get("port") or 22),
            username=server_cfg.get("username") or None,
            password=server_cfg.get("password") or None,
            known_hosts=None,
            connect_timeout=settings.ssh_connect_timeout,
        ) as conn:
            result = await asyncio.wait_for(
                conn.run("bash -s", input=content, env={"TERM": "xterm"}),
                settings.ssh_command_timeout * 6,
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
    except (asyncio.TimeoutError, TimeoutError):
        timed_out = True
    except (OSError, asyncssh.Error) as e:
        await oplog.record(site_id, log_resource, "SSH_SCRIPT_RUN",
                           target=log_target,
                           params={"server": server_cfg["host"], "triggered": triggered},
                           result="FAILED", error=str(e)[:200])
        raise NotFound(f"SSH 执行失败：{e}") from None

    await oplog.record(site_id, log_resource, "SSH_SCRIPT_RUN",
                       target=log_target,
                       params={"server": server_cfg["host"], "triggered": triggered,
                               "timed_out": timed_out})
    return {
        "stdout": stdout[-50_000:],
        "stderr": stderr[-10_000:],
        "timed_out": timed_out,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


async def run_script(site_id: str, script_id: str, *, triggered: str = "manual") -> dict[str, Any]:
    """按脚本 id 执行（手动/定时共用；记录 oplog）。"""
    script = await get_script(site_id, script_id)
    if not script:
        raise NotFound(f"script not found: {script_id}")
    server_cfg = await get_resource_raw(site_id, "servers", script.get("server_id") or "")
    if not server_cfg:
        raise NotFound(f"绑定的 Server 配置不存在: {script.get('server_id')}")
    content = str(script.get("content") or "")
    if not content.strip():
        raise ValueError("脚本内容为空")
    return await _execute(server_cfg, content, site_id=site_id,
                          log_resource=f"ssh_scripts/{script_id}",
                          log_target=script["name"], triggered=triggered)


async def run_adhoc(site_id: str, server_id: str, content: str) -> dict[str, Any]:
    """编辑弹窗内的“测试”：直接执行表单内容，不创建、不保存脚本。"""
    server_cfg = await get_resource_raw(site_id, "servers", server_id)
    if not server_cfg:
        raise NotFound(f"绑定的 Server 配置不存在: {server_id}")
    if not (content or "").strip():
        raise ValueError("脚本内容为空")
    return await _execute(server_cfg, content, site_id=site_id,
                          log_resource="ssh_adhoc", log_target="(test)",
                          triggered="test")


# 服务器时区缓存：{server_id: (tzinfo, label)}；进程内缓存足够（服务器时区几乎不变）
# ponytail: 无过期，服务器时区变更需重启后端
_TZ_CACHE: dict[str, tuple] = {}


async def get_server_tz(site_id: str | None, server_id: str | None):
    """目标服务器的时区：SSH 执行 date +%z 解析为 UTC 偏移。失败回退 UTC。"""
    from datetime import timedelta, timezone

    if not site_id or not server_id:
        return timezone.utc, "UTC"
    if server_id in _TZ_CACHE:
        return _TZ_CACHE[server_id]
    try:
        server_cfg = await get_resource_raw(site_id, "servers", server_id)
        if not server_cfg:
            raise NotFound("server not found")
        async with asyncssh.connect(
            server_cfg["host"], port=int(server_cfg.get("port") or 22),
            username=server_cfg.get("username") or None,
            password=server_cfg.get("password") or None,
            known_hosts=None, connect_timeout=3,
        ) as conn:
            res = await conn.run("date +%z", check=False)
            off = (res.stdout or "").strip()  # 如 +0800 / -0530
        sign = -1 if off.startswith("-") else 1
        digits = off.lstrip("+-")
        hours, minutes = int(digits[:2] or 0), int(digits[2:4] or 0)
        tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
        label = f"UTC{'+' if sign > 0 else '-'}{hours:02d}:{minutes:02d}"
    except Exception:  # noqa: BLE001 - 任何失败回退 UTC
        tz, label = timezone.utc, "UTC"
    _TZ_CACHE[server_id] = (tz, label)
    return tz, label
