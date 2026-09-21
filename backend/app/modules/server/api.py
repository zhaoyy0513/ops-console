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
