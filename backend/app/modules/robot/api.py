from fastapi import APIRouter, HTTPException

from backend.app.modules.robot import service
from backend.app.modules.sites.service import NotFound

router = APIRouter(tags=["robot"])


@router.get("/sites/{site_id}/robots")
async def list_robots(site_id: str) -> list[dict]:
    """站点下每个启用的 Robot 实例聚合其机器人列表（PRD §18）。"""
    from backend.app.modules.sites import service as sites_service

    try:
        instances = await sites_service.list_resources(site_id, "robots")
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    robots: list[dict] = []
    for inst in instances:
        if not inst.get("enabled", True):
            continue
        try:
            items = await service.list_robots(site_id, inst["id"])
        except service.OpsError:
            items = []  # 单实例失败不影响其他（验收 7）
        for item in items:
            item["instance"] = inst["id"]
            robots.append(item)
    return robots


@router.get("/sites/{site_id}/robots/{robot_id}")
async def get_robot(site_id: str, robot_id: str, instance: str | None = None) -> dict:
    """robot_id 为业务 Robot ID；实例经 query 参数指定（单实例站点可省略）。"""
    from backend.app.modules.sites import service as sites_service

    try:
        instances = await sites_service.list_resources(site_id, "robots")
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    targets = [i for i in instances if i.get("enabled", True) and (not instance or i["id"] == instance)]
    last_error: Exception | None = None
    for inst in targets:
        try:
            detail = await service.get_robot(site_id, inst["id"], robot_id)
            detail["instance"] = inst["id"]
            return detail
        except (service.OpsError, Exception) as e:  # noqa: BLE001 - 逐实例尝试
            last_error = e
    if last_error:
        raise HTTPException(status_code=502, detail=str(last_error))
    raise HTTPException(status_code=404, detail=f"robot not found: {robot_id}")
