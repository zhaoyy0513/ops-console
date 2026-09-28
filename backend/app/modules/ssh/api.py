import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.modules.sites.service import NotFound
from backend.app.modules.ssh import scheduling
from backend.app.modules.ssh import service

router = APIRouter(tags=["ssh-scripts"])


class ScriptIn(BaseModel):
    id: str | None = None  # 可自定义 id（不传自动生成）
    name: str
    server_id: str
    content: str
    enabled: bool = True
    cron: str | None = None  # 非空 = 定时脚本（标准 5 段 cronie 格式）


class ScriptUpdate(BaseModel):
    name: str | None = None
    server_id: str | None = None
    content: str | None = None
    enabled: bool | None = None
    cron: str | None = None
    sched_enabled: bool | None = None  # 定时开关（仅定时脚本有意义）


class CronIn(BaseModel):
    cron: str


class RunAdhocIn(BaseModel):
    server_id: str
    content: str


@router.get("/sites/{site_id}/ssh_scripts")
async def list_scripts(site_id: str) -> list[dict]:
    try:
        return await service.list_scripts(site_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/sites/{site_id}/ssh_scripts", status_code=201)
async def create_script(site_id: str, data: ScriptIn) -> dict:
    _validate_cron_field(data.cron)
    try:
        item = await service.create_script(site_id, data.model_dump())
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    scheduling.sync_one(site_id, item)  # 新建强制 sched_enabled=False，sync 为 no-op
    return item


@router.put("/sites/{site_id}/ssh_scripts/{script_id}")
async def update_script(site_id: str, script_id: str, data: ScriptUpdate) -> dict:
    try:
        item = await service.update_script(
            site_id, script_id, data.model_dump(exclude_none=True))
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    if item is None:
        raise HTTPException(status_code=404, detail=f"script not found: {script_id}")
    _validate_cron_field(item.get("cron"))
    scheduling.sync_one(site_id, item)  # cron/开关变更后同步定时 job
    return item


@router.delete("/sites/{site_id}/ssh_scripts/{script_id}", status_code=204)
async def delete_script(site_id: str, script_id: str) -> None:
    try:
        deleted = await service.delete_script(site_id, script_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    scheduling.unschedule(site_id, script_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"script not found: {script_id}")


@router.post("/sites/{site_id}/ssh_scripts/{script_id}/run")
async def run_script(site_id: str, script_id: str) -> dict:
    """在绑定的 Server 上执行脚本（手动触发；60s 上限，记录 oplog）。"""
    try:
        return await service.run_script(site_id, script_id, triggered="manual")
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/sites/{site_id}/ssh_scripts/run-adhoc")
async def run_adhoc(site_id: str, data: RunAdhocIn) -> dict:
    """编辑弹窗测试：直接执行表单内容（不落库，oplog 记 ssh_adhoc）。"""
    try:
        return await service.run_adhoc(site_id, data.server_id, data.content)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


def _sse(kind: str, data: str) -> str:
    return f"data: {json.dumps({'kind': kind, 'data': data}, ensure_ascii=False)}\n\n"


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


@router.post("/ssh/validate-cron")
async def validate_cron(data: CronIn) -> dict:
    """校验 cron 表达式并返回未来 3 次执行时间（标准 5 段 cronie 格式）。"""
    from datetime import datetime, timezone

    from croniter import croniter

    try:
        it = croniter(data.cron, datetime.now(timezone.utc))
        next_times = [it.get_next(datetime) for _ in range(3)]
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=f"无效 cron 表达式：{e}") from None

    return {
        "valid": True,
        "tz_label": "UTC",
        "next_runs": [t.strftime("%Y-%m-%d %H:%M:%S") for t in next_times],
    }


def _validate_cron_field(cron: str | None) -> None:
    if not cron:
        return
    from croniter import croniter

    try:
        croniter(cron)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=f"无效 cron 表达式：{e}") from None
