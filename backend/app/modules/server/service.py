"""Server 模块服务层：provider 构建、缓存合并、连接测试。"""

import json
import re
import time
from typing import Any

from backend.app.core import oplog, sampling
from backend.app.core.cache import cached
from backend.app.core.redis import get_platform_redis
from backend.app.modules.server.provider import SSHServerMetricsProvider
from backend.app.modules.sites.service import NotFound
from backend.app.shared import testconn
from backend.app.shared.errors import OpsError
from backend.app.shared.retry import with_retry
from backend.app.shared.concurrency import get_semaphore

CACHE_TTL = 3  # 与前端 3s 轮询对齐：每次轮询都能拿到新数据（单飞锁防重复 SSH）

_PID_RE = re.compile(r"^\d+$")  # kill 的 pid 必须纯数字：合法性校验 + 杜绝命令注入


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
    key = f"ops:cache:server:{server_id}:{kind}"  # 与 cached() 内部 key 一致
    # 缓存命中不占信号量（死服务器风暴时 3s 读不会挤占慢路径）
    raw = await get_platform_redis().get(key)
    if raw is not None:
        return json.loads(raw)
    async with get_semaphore("ssh"):
        # 读路径套连接级有限重试（PRD §26）；写路径无此资源
        return await cached(key, CACHE_TTL, with_retry(factory))


async def get_metrics(site_id: str, server_id: str) -> dict[str, Any]:
    from backend.app.modules.server.diagnosis import diagnose, merge_thresholds
    from backend.app.modules.sites import service as sites_service

    config = await _require_server_config(site_id, server_id)
    site = await sites_service.get_site(site_id)

    def factory():
        provider = _build_provider(config)
        return provider.get_metrics()

    # 采样挂在真实读取上（前端 3s 轮询驱动，趋势点随页面在场密度变高）
    # key 带站点维度：不同站点的同名资源 id 互不污染
    async def sampled_factory():
        metrics = await factory()
        cpu = metrics.get("cpu", {}).get("usage")
        mem = metrics.get("memory", {})
        mem_pct = (round(mem["used"] / mem["total"] * 100, 1)
                   if mem.get("total") and mem.get("used") is not None else None)
        rid = f"server:{site_id}:{server_id}"
        if isinstance(cpu, (int, float)):
            await sampling.push_sample(rid, "cpu", cpu)
        if isinstance(mem_pct, (int, float)):
            await sampling.push_sample(rid, "mem", mem_pct)
        return metrics

    metrics = await _with_cache(site_id, server_id, "metrics", sampled_factory)
    # 诊断不走缓存值缓存，但用同一份 metrics 计算，零额外 SSH
    thresholds = merge_thresholds(config.get("thresholds"), (site or {}).get("thresholds"))
    return {**metrics, "diagnosis": diagnose(metrics, thresholds)}


async def get_processes(site_id: str, server_id: str) -> list[dict[str, Any]]:
    config = await _require_server_config(site_id, server_id)
    provider = _build_provider(config)
    return await _with_cache(site_id, server_id, "processes", provider.get_processes)


async def get_zombies(site_id: str, server_id: str) -> dict[str, Any]:
    """僵尸进程明细（按父进程分组 {total, groups}）。不走缓存：kill 后立即重读，避免 3s 旧值里还躺着已终止的进程。"""
    config = await _require_server_config(site_id, server_id)
    provider = _build_provider(config)
    async with get_semaphore("ssh"):
        return await provider.get_zombies()


async def kill_zombie(site_id: str, server_id: str, pid: str, comm: str | None = None) -> dict[str, Any]:
    """kill -9 远端僵尸进程（写路径：无重试；记 oplog，PRD §17）。"""
    if not _PID_RE.fullmatch(pid):
        raise OpsError("INVALID_OPERATION", f"invalid pid: {pid}", status_code=400)
    config = await _require_server_config(site_id, server_id)
    provider = _build_provider(config)
    async with get_semaphore("ssh"):
        try:
            await provider.kill_zombie(int(pid))
        except OpsError as e:
            # 失败也留痕（PRD §17）：先记 FAILED 再原样抛给统一错误包络
            await oplog.record(
                site_id, f"server/{config.get('name') or server_id}", "SERVER_KILL_ZOMBIE",
                target=f"{pid} {comm}" if comm else pid,
                params={"pid": int(pid), "comm": comm, "host": config.get("host")},
                result="FAILED", error=str(e)[:200],
            )
            raise
    # oplog 可读性：resource 用 Server 名（内部 id 移入 params，oplog.record docstring 约定）
    await oplog.record(
        site_id, f"server/{config.get('name') or server_id}", "SERVER_KILL_ZOMBIE",
        target=f"{pid} {comm}" if comm else pid,
        params={"pid": int(pid), "comm": comm, "host": config.get("host")},
    )
    return {"killed": True}


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
