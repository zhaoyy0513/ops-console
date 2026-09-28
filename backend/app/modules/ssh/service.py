"""SSH 脚本模块：绑定 Server 的脚本管理与受控执行（站点级）。

脚本存储：ops:site:{site_id}:ssh_scripts Hash（id -> JSON）。
执行：asyncssh 连接脚本绑定的 Server，脚本内容经 stdin 交给远端
`bash -s` 子进程，收集 stdout/stderr 后返回（同步等待，60s 上限）。
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


def _parse(raw: str) -> dict[str, Any]:
    return json.loads(raw)


async def list_scripts(site_id: str) -> list[dict[str, Any]]:
    await _require_site(site_id)
    raw = await get_platform_redis().hvals(_key(site_id))
    items = [json.loads(x) for x in raw]
    return sorted(items, key=lambda s: s["name"])


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
    data = {**data, "id": script_id}
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


async def run_script(site_id: str, script_id: str) -> dict[str, Any]:
    """在绑定的 Server 上以远端 bash -s 子进程执行脚本，收集完整输出。

    超时 60s；执行与结果记录操作日志（脚本名 + 目标 server）。
    """
    script = await get_script(site_id, script_id)
    if not script:
        raise NotFound(f"script not found: {script_id}")
    server_cfg = await get_resource_raw(site_id, "servers", script.get("server_id") or "")
    if not server_cfg:
        raise NotFound(f"绑定的 Server 配置不存在: {script.get('server_id')}")

    content = str(script.get("content") or "")
    if not content.strip():
        raise ValueError("脚本内容为空")

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
        await oplog.record(site_id, f"ssh_scripts/{script_id}", "SSH_SCRIPT_RUN",
                           target=script["name"], params={"server": server_cfg["host"]},
                           result="FAILED", error=str(e)[:200])
        raise NotFound(f"SSH 执行失败：{e}") from None

    await oplog.record(site_id, f"ssh_scripts/{script_id}", "SSH_SCRIPT_RUN",
                       target=script["name"],
                       params={"server": server_cfg["host"], "timed_out": timed_out})
    return {
        "stdout": stdout[-50_000:],  # 防超大输出撑爆前端
        "stderr": stderr[-10_000:],
        "timed_out": timed_out,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }
