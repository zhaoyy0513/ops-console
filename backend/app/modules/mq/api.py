from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


class EmptyQueueIn(BaseModel):
    mbean: str  # 队列完整 ObjectName（来自 Topics/Queues 列表的 _mbean）
    queue: str  # 队列名（仅用于操作日志展示）


@router.post("/sites/{site_id}/mq/{mq_id}/queues/empty")
async def empty_queue(site_id: str, mq_id: str, body: EmptyQueueIn) -> dict:
    """清空队列积压消息（用户要求的运维操作；记录操作日志）。"""
    try:
        return await service.empty_queue(site_id, mq_id, body.mbean, body.queue)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except service.OpsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from None


@router.get("/sites/{site_id}/mq/{mq_id}/queues/messages")
async def browse_queue_messages(site_id: str, mq_id: str, mbean: str, queue: str,
                                limit: int = 20) -> list[dict]:
    """浏览队列内消息（QueueControl.browse()，只读预览，默认前 20 条）。"""
    try:
        return await service.browse_queue(site_id, mq_id, mbean, queue, limit)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except service.OpsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from None
