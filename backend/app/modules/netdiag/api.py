from fastapi import APIRouter, HTTPException

from . import service

router = APIRouter(tags=["netdiag"])


@router.get("/netdiag/{site_id}/matrix")
async def get_matrix(site_id: str) -> list[dict]:
    """当前站点已配置资源的 TCP 连通性矩阵（后端出站探测）。"""
    try:
        return await service.matrix(site_id)
    except service.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
