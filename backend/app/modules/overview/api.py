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


@router.get("/samples")
async def get_samples(rid: str, series: str, limit: int = 60) -> list[dict]:
    """采样序列查询（趋势图数据源）：rid 形如 server:<site>:<id> / mq:<site>:<id>。"""
    from backend.app.core.sampling import read_series

    # 仅允许安全的 key 组成部分，防止拼出任意 Redis key
    if not rid or not series or any(c in rid + series for c in " {}*?\0\n"):
        raise HTTPException(status_code=400, detail="invalid rid/series")
    try:
        return await read_series(rid, series, limit)
    except Exception:  # noqa: BLE001 - 采样读失败降级为空（趋势图缺数据不该 500）
        return []
