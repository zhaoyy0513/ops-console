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
from backend.app.shared.concurrency import get_host_semaphore, get_semaphore

SCRIPTS_KEY = "ops:site:{site_id}:ssh_scripts"
RUN_TIMEOUT = 60


def _bash_cmd() -> str:
    """远端命令统一加 GNU timeout 前缀：超时信号发至整个进程组——

    本地 kill 只能杀 bash -s，其子进程（top、tail -f）会被 reparent 存活
    （无 pty 不吃 SIGHUP）；timeout 默认信号打给子进程所在进程组，能全树清掉。
    远端 预算-5s TERM + 5s KILL，本地 wait_for（预算全额）仍是兜底。
    """
    return f"timeout -k 5 {settings.ssh_command_timeout * 6 - 5} bash -s"


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


def _server_label(server_cfg: dict[str, Any]) -> str:
    """oplog 展示用 Server 标识：name 优先，host 兜底。"""
    return str(server_cfg.get("name") or server_cfg.get("host") or "?")


async def _execute(server_cfg: dict[str, Any], content: str, *,
                   site_id: str, log_resource: str, log_target: str,
                   triggered: str, log_extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """在指定 Server 上执行脚本内容（共享执行体：按 id 执行与 adhoc 测试共用）。

    实时刷新型命令（top/docker stats）永不退出，会跑满超时——超时后
    kill 进程但保留已产出输出返回（而非只报失败）。对退出型命令无影响。
    """
    import asyncio
    import time

    started = time.perf_counter()
    timed_out = False
    stdout = ""
    stderr = ""
    proc = None
    # 双层级流：ssh_run 独立池（流式执行合法持锁 60s，不得挤占 "ssh"/8 池上的
    # 3s 指标轮询）+ 按主机限流（同一台机并发脚本堆积有上界）。
    # 手动/adhoc/cron/双 SSE 流全部经由此函数或 stream_execute，覆盖全部入口。
    async with get_semaphore("ssh_run", 4), get_host_semaphore(server_cfg["host"]):
        try:
            async with asyncssh.connect(
                server_cfg["host"],
                port=int(server_cfg.get("port") or 22),
                username=server_cfg.get("username") or None,
                password=server_cfg.get("password") or None,
                known_hosts=None,
                connect_timeout=settings.ssh_connect_timeout,
            ) as conn:
                proc = await conn.create_process(_bash_cmd(), env={"TERM": "xterm"})
                proc.stdin.write(content)
                proc.stdin.write_eof()
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), settings.ssh_command_timeout * 6)
                    stdout, stderr = stdout or "", stderr or ""
                except (asyncio.TimeoutError, TimeoutError):
                    timed_out = True
                    # 超时：kill 进程，尽力回收已产出输出（top 类命令此时已有画面）
                    try:
                        proc.kill()
                    except (ProcessLookupError, asyncssh.Error):
                        pass
                    try:
                        stdout, stderr = await asyncio.wait_for(proc.communicate(), 2)
                        stdout, stderr = stdout or "", stderr or ""
                    except Exception:  # noqa: BLE001 - 回收失败不影响超时路径
                        pass
        except (OSError, asyncssh.Error) as e:
            await oplog.record(site_id, log_resource, "SSH_SCRIPT_RUN",
                               target=log_target,
                               params={**(log_extra or {}), "server": server_cfg["host"], "triggered": triggered},
                               result="FAILED", error=str(e)[:200])
            raise NotFound(f"SSH 执行失败：{e}") from None
        finally:
            if proc is not None:
                try:
                    proc.close()  # 兜底清理（幂等）
                except Exception:  # noqa: BLE001
                    pass

    await oplog.record(site_id, log_resource, "SSH_SCRIPT_RUN",
                       target=log_target,
                       params={**(log_extra or {}), "server": server_cfg["host"], "triggered": triggered,
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
                          log_resource=f"ssh/{_server_label(server_cfg)}",
                          log_target=script["name"], triggered=triggered,
                          log_extra={"script_id": script_id})


async def run_adhoc(site_id: str, server_id: str, content: str) -> dict[str, Any]:
    """编辑弹窗内的“测试”：直接执行表单内容，不创建、不保存脚本。"""
    server_cfg = await get_resource_raw(site_id, "servers", server_id)
    if not server_cfg:
        raise NotFound(f"绑定的 Server 配置不存在: {server_id}")
    if not (content or "").strip():
        raise ValueError("脚本内容为空")
    return await _execute(server_cfg, content, site_id=site_id,
                          log_resource=f"ssh/{_server_label(server_cfg)}",
                          log_target=f"adhoc@{_server_label(server_cfg)}", triggered="test")


async def stream_execute(server_cfg: dict[str, Any], content: str, *,
                        site_id: str, log_resource: str, log_target: str,
                        triggered: str, log_extra: dict[str, Any] | None = None):
    """流式执行：边产出边 yield (kind, chunk)，kind in {stdout, stderr}。

    - 整体预算 settings.ssh_command_timeout * 6 秒，到点 kill 并 yield 终态；
    - 客户端断开（FastAPI 取消生成器）时 finally 中 kill，绝不遗留远端进程；
    - stdout/stderr 两个 reader 并发读入同一队列（串行轮询会让 stderr
      在 stdout 不退出时永远读不到——如 docker stats 刷新中对 stderr 的告警）；
    - 结束 yield ("meta", json) 携带 timed_out / latency_ms。
    """
    import asyncio
    import json
    import time

    started = time.perf_counter()
    timeout = settings.ssh_command_timeout * 6
    proc = None
    timed_out = False
    logged = False  # FAILED 分支已写 oplog，finally 不重复记
    async with get_semaphore("ssh_run", 4), get_host_semaphore(server_cfg["host"]):
        try:
            async with asyncssh.connect(
                server_cfg["host"],
                port=int(server_cfg.get("port") or 22),
                username=server_cfg.get("username") or None,
                password=server_cfg.get("password") or None,
                known_hosts=None,
                connect_timeout=settings.ssh_connect_timeout,
            ) as conn:
                proc = await conn.create_process(_bash_cmd(), env={"TERM": "xterm"})
                proc.stdin.write(content)
                proc.stdin.write_eof()

                # maxsize=1000：读端背压进 SSH channel 窗口，yes 类洪流
                # 在 60s 预算内也撑不爆后端内存
                queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

                async def reader(stream, kind):
                    try:
                        while True:
                            chunk = await stream.read(4096)
                            if not chunk:
                                return
                            await queue.put((kind, chunk))
                    finally:
                        # 队列满时放弃哨兵：正常 EOF 时消费端在高速读、put 不会满；
                        # 满载只发生在取消路径（消费端已不在，哨兵无人消费）或
                        # 洪流场景（整体预算兜底），阻塞 put 反而会吊死已取消的任务
                        try:
                            queue.put_nowait((None, None))
                        except asyncio.QueueFull:
                            pass

                tasks = [
                    asyncio.create_task(reader(proc.stdout, "stdout")),
                    asyncio.create_task(reader(proc.stderr, "stderr")),
                ]
                try:
                    deadline = time.monotonic() + timeout
                    eof = 0
                    while eof < 2:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            timed_out = True
                            break
                        try:
                            kind, chunk = await asyncio.wait_for(queue.get(), remaining)
                        except (asyncio.TimeoutError, TimeoutError):
                            timed_out = True
                            break
                        if kind is None:
                            eof += 1
                        else:
                            yield kind, chunk
                finally:
                    for t in tasks:
                        t.cancel()
        except (OSError, asyncssh.Error) as e:
            logged = True
            await oplog.record(site_id, log_resource, "SSH_SCRIPT_RUN",
                               target=log_target,
                               params={**(log_extra or {}), "server": server_cfg["host"], "triggered": triggered},
                               result="FAILED", error=str(e)[:200])
            raise NotFound(f"SSH 执行失败：{e}") from None
        finally:
            if proc is not None:
                try:
                    proc.kill()  # 幂等：正常退出后 kill 是 no-op；断开/超时则终止远端进程
                except Exception:  # noqa: BLE001
                    pass
                try:
                    proc.close()
                except Exception:  # noqa: BLE001
                    pass
            # oplog 收尾放在 finally：客户端断开（GeneratorExit 穿过 yield 点）
            # 也会走到这里，断开不再漏记；redis 故障吞掉，不掩盖 unwind
            if not logged:
                logged = True
                try:
                    await oplog.record(site_id, log_resource, "SSH_SCRIPT_RUN",
                                       target=log_target,
                                       params={**(log_extra or {}), "server": server_cfg["host"],
                                               "triggered": triggered, "timed_out": timed_out})
                except Exception:  # noqa: BLE001
                    pass

    yield "meta", json.dumps({
        "timed_out": timed_out,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    })


async def stream_script(site_id: str, script_id: str, *, triggered: str = "manual"):
    script = await get_script(site_id, script_id)
    if not script:
        raise NotFound(f"script not found: {script_id}")
    server_cfg = await get_resource_raw(site_id, "servers", script.get("server_id") or "")
    if not server_cfg:
        raise NotFound(f"绑定的 Server 配置不存在: {script.get('server_id')}")
    content = str(script.get("content") or "")
    if not content.strip():
        raise ValueError("脚本内容为空")
    async for item in stream_execute(server_cfg, content, site_id=site_id,
                                     log_resource=f"ssh/{_server_label(server_cfg)}",
                                     log_target=script["name"], triggered=triggered,
                                     log_extra={"script_id": script_id}):
        yield item


async def stream_adhoc(site_id: str, server_id: str, content: str):
    server_cfg = await get_resource_raw(site_id, "servers", server_id)
    if not server_cfg:
        raise NotFound(f"绑定的 Server 配置不存在: {server_id}")
    if not (content or "").strip():
        raise ValueError("脚本内容为空")
    async for item in stream_execute(server_cfg, content, site_id=site_id,
                                     log_resource=f"ssh/{_server_label(server_cfg)}",
                                     log_target=f"adhoc@{_server_label(server_cfg)}",
                                     triggered="test"):
        yield item
