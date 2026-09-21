from fastapi import APIRouter, HTTPException

from backend.app.modules.overview import service
from backend.app.modules.sites.service import NotFound

router = APIRouter(tags=["overview"])


@router.get("/sites/{site_id}/overview")
async def get_overview(site_id: str) -> dict:
    try:
        return await service.get_overview(site_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/sites/{site_id}/overview/refresh")
async def refresh(site_id: str) -> dict:
    """手动触发单站点健康检查（不等 30s 周期）。"""
    try:
        count = await service.check_site(site_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from None
    return {"checked": count}
