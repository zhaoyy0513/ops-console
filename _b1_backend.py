# -*- coding: utf-8 -*-
"""Batch1: SSH 流式执行（后端 SSE + 前端实时渲染 + 关闭即杀进程）"""
# ---------- backend service: stream_execute ----------
p = 'backend/app/modules/ssh/service.py'
s = open(p, encoding='utf-8').read()
s = s.rstrip() + '''


async def stream_execute(server_cfg: dict[str, Any], content: str, *,
                        site_id: str, log_resource: str, log_target: str,
                        triggered: str):
    """流式执行：边产出边 yield (kind, chunk)，kind in {stdout, stderr}。

    - 整体预算 settings.ssh_command_timeout * 6 秒，到点 kill 并 yield 终态；
    - 客户端断开（FastUI 取消生成器）时 finally 中 kill，绝不遗留远端进程；
    - 结束 yield ("meta", json) 携带 timed_out / latency_ms。
    """
    import asyncio
    import json
    import time

    started = time.perf_counter()
    timeout = settings.ssh_command_timeout * 6
    proc = None
    timed_out = False
    try:
        async with asyncssh.connect(
            server_cfg["host"],
            port=int(server_cfg.get("port") or 22),
            username=server_cfg.get("username") or None,
            password=server_cfg.get("password") or None,
            known_hosts=None,
            connect_timeout=settings.ssh_connect_timeout,
        ) as conn:
            proc = await conn.create_process("bash -s", env={"TERM": "xterm"})
            proc.stdin.write(content)
            proc.stdin.write_eof()

            async def pump(stream, kind):
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    chunk = await asyncio.wait_for(stream.read(4096), remaining)
                    if not chunk:
                        return
                    yield kind, chunk

            deadline = time.monotonic() + timeout
            pumps = [
                pump(proc.stdout, "stdout"),
                pump(proc.stderr, "stderr"),
            ]
            while pumps:
                done, pending = set(), set()
                # 用 as_completed 语义手工调度：任一泵产出立即转发
                try:
                    for gen in pumps:
                        try:
                            kind, chunk = await gen.__anext__()
                            yield kind, chunk
                            done.add(gen)
                            break
                        except StopAsyncIteration:
                            pumps.remove(gen)
                            break
                except TimeoutError:
                    timed_out = True
                    break
                # 一轮只取一个泵的一块后重新排队（简化轮询）
                if not pumps:
                    break
    except (OSError, asyncssh.Error) as e:
        await oplog.record(site_id, log_resource, "SSH_SCRIPT_RUN",
                           target=log_target,
                           params={"server": server_cfg["host"], "triggered": triggered},
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

    await oplog.record(site_id, log_resource, "SSH_SCRIPT_RUN",
                       target=log_target,
                       params={"server": server_cfg["host"], "triggered": triggered,
                               "timed_out": timed_out})
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
                                     log_resource=f"ssh_scripts/{script_id}",
                                     log_target=script["name"], triggered=triggered):
        yield item


async def stream_adhoc(site_id: str, server_id: str, content: str):
    server_cfg = await get_resource_raw(site_id, "servers", server_id)
    if not server_cfg:
        raise NotFound(f"绑定的 Server 配置不存在: {server_id}")
    if not (content or "").strip():
        raise ValueError("脚本内容为空")
    async for item in stream_execute(server_cfg, content, site_id=site_id,
                                     log_resource="ssh_adhoc", log_target="(test)",
                                     triggered="test"):
        yield item
'''
open(p, 'w', encoding='utf-8').write(s)
print('service ok')

# ---------- backend api: SSE endpoints ----------
p = 'backend/app/modules/ssh/api.py'
s = open(p, encoding='utf-8').read()
s = s.replace(
    "from fastapi import APIRouter, HTTPException",
    "import json\n\nfrom fastapi import APIRouter, HTTPException\nfrom fastapi.responses import StreamingResponse")
s = s.replace(
    '''@router.post("/ssh/validate-cron")''',
    '''def _sse(kind: str, data: str) -> str:
    return f"data: {json.dumps({'kind': kind, 'data': data}, ensure_ascii=False)}\\n\\n"


@router.post("/sites/{site_id}/ssh_scripts/{script_id}/run-stream")
async def run_script_stream(site_id: str, script_id: str) -> StreamingResponse:
    """流式执行（SSE）：输出实时推送；客户端断开即 kill 远端进程。"""
    async def gen():
        try:
            async for kind, data in service.stream_script(site_id, script_id):
                yield _sse(kind, data)
        except NotFound as e:
            yield _sse("error", str(e))
        except ValueError as e:
            yield _sse("error", str(e))

    return StreamingResponse(gen(), media_type="text/event-stream",
                            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/sites/{site_id}/ssh_scripts/run-adhoc-stream")
async def run_adhoc_stream(site_id: str, data: RunAdhocIn) -> StreamingResponse:
    """编辑弹窗测试（流式）：直接执行表单内容，不落库；断开即杀进程。"""
    async def gen():
        try:
            async for kind, chunk in service.stream_adhoc(site_id, data.server_id, data.content):
                yield _sse(kind, chunk)
        except NotFound as e:
            yield _sse("error", str(e))
        except ValueError as e:
            yield _sse("error", str(e))

    return StreamingResponse(gen(), media_type="text/event-stream",
                            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/ssh/validate-cron")''')
open(p, 'w', encoding='utf-').write(s)
print('api ok')
