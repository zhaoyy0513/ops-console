from fastapi import APIRouter, HTTPException

from backend.app.modules.mq import service
from backend.app.modules.sites.service import NotFound

router = APIRouter(tags=["mq"])


@router.get("/sites/{site_id}/mq/{mq_id}/overview")
async def get_overview(site_id: str, mq_id: str) -> dict:
    try:
        return await service.get_overview(site_id, mq_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.get("/sites/{site_id}/mq/{mq_id}/queues")
async def get_queues(site_id: str, mq_id: str) -> list[dict]:
    try:
        return await service.get_queues(site_id, mq_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.get("/sites/{site_id}/mq/{mq_id}/addresses")
async def get_addresses(site_id: str, mq_id: str) -> list[dict]:
    try:
        return await service.get_addresses(site_id, mq_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
