from fastapi import APIRouter, HTTPException

from backend.app.modules.server import service
from backend.app.modules.sites.service import NotFound

router = APIRouter(tags=["server"])


@router.get("/sites/{site_id}/servers/{server_id}/metrics")
async def get_metrics(site_id: str, server_id: str) -> dict:
    try:
        return await service.get_metrics(site_id, server_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.get("/sites/{site_id}/servers/{server_id}/processes")
async def get_processes(site_id: str, server_id: str) -> list[dict]:
    try:
        return await service.get_processes(site_id, server_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.get("/sites/{site_id}/servers/{server_id}/zombies")
async def get_zombies(site_id: str, server_id: str) -> dict:
    """僵尸进程按父进程分组 {total, groups:[{ppid, count, cmd}]}（与 metrics 同一条 SSH 命令路径）。"""
    try:
        return await service.get_zombies(site_id, server_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/sites/{site_id}/servers/{server_id}/zombies/{pid}/kill")
async def kill_zombie(site_id: str, server_id: str, pid: str, comm: str | None = None) -> dict:
    """kill -9 指定僵尸进程（pid 纯数字校验；comm 仅用于 oplog 展示）。"""
    try:
        return await service.kill_zombie(site_id, server_id, pid, comm)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
