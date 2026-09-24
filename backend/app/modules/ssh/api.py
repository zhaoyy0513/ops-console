from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.modules.sites.service import NotFound
from backend.app.modules.ssh import service

router = APIRouter(tags=["ssh-scripts"])


class ScriptIn(BaseModel):
    name: str
    server_id: str
    content: str
    enabled: bool = True


class ScriptUpdate(BaseModel):
    name: str | None = None
    server_id: str | None = None
    content: str | None = None
    enabled: bool | None = None


@router.get("/sites/{site_id}/ssh_scripts")
async def list_scripts(site_id: str) -> list[dict]:
    try:
        return await service.list_scripts(site_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/sites/{site_id}/ssh_scripts", status_code=201)
async def create_script(site_id: str, data: ScriptIn) -> dict:
    try:
        return await service.create_script(site_id, data.model_dump())
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


@router.put("/sites/{site_id}/ssh_scripts/{script_id}")
async def update_script(site_id: str, script_id: str, data: ScriptUpdate) -> dict:
    try:
        item = await service.update_script(
            site_id, script_id, data.model_dump(exclude_none=True))
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    if item is None:
        raise HTTPException(status_code=404, detail=f"script not found: {script_id}")
    return item


@router.delete("/sites/{site_id}/ssh_scripts/{script_id}", status_code=204)
async def delete_script(site_id: str, script_id: str) -> None:
    try:
        deleted = await service.delete_script(site_id, script_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    if not deleted:
        raise HTTPException(status_code=404, detail=f"script not found: {script_id}")


@router.post("/sites/{site_id}/ssh_scripts/{script_id}/run")
async def run_script(site_id: str, script_id: str) -> dict:
    """在绑定的 Server 上执行脚本（远端 bash -s 子进程，60s 上限，记录 oplog）。"""
    try:
        return await service.run_script(site_id, script_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
