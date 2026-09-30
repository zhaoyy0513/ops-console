from fastapi import APIRouter, HTTPException

from backend.app.modules.device import service
from backend.app.modules.sites.service import NotFound

router = APIRouter(tags=["device"])


@router.get("/sites/{site_id}/device-instances/{device_id}/sample-fields")
async def get_sample_fields(site_id: str, device_id: str) -> dict:
    """取一条原始 JSON 数据及其字段名（字段映射配置用）。"""
    try:
        return await service.get_raw_sample(site_id, device_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.get("/devices/mappings")
async def list_device_mappings() -> list[dict]:
    """全局列出所有站点 Device 实例的字段映射配置（克隆功能用，不分站点）。"""
    from backend.app.modules.sites import service as sites_service

    out: list[dict] = []
    for site in await sites_service.list_sites():
        for inst in await sites_service.list_resources(site["id"], "devices"):
            out.append({
                "site_id": site["id"],
                "site_name": site["name"],
                "device_id": inst["id"],
                "device_name": inst["name"],
                "field_map": inst.get("field_map"),
                "value_map": inst.get("value_map"),
                "custom_fields": inst.get("custom_fields"),  # 克隆需连同自定义字段一起复制
            })
    return out


@router.get("/sites/{site_id}/devices")
async def list_devices(site_id: str, instance: str | None = None) -> list[dict]:
    """列出设备；instance 指定单个实例（页面下拉选择），缺省聚合全部启用实例。"""
    from backend.app.modules.sites import service as sites_service

    try:
        instances = await sites_service.list_resources(site_id, "devices")
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    devices: list[dict] = []
    for inst in instances:
        if not inst.get("enabled", True):
            continue
        if instance and inst["id"] != instance:
            continue
        try:
            items = await service.list_devices(site_id, inst["id"])
        except service.OpsError:
            items = []  # 单实例失败不影响其他（验收 7）
        for item in items:
            item["instance"] = inst["id"]
            devices.append(item)
    return devices


@router.get("/sites/{site_id}/devices/{device_id}")
async def get_device(site_id: str, device_id: str, instance: str | None = None) -> dict:
    """device_id 为业务 Device ID；实例经 query 参数指定（单实例站点可省略）。"""
    from backend.app.modules.sites import service as sites_service

    try:
        instances = await sites_service.list_resources(site_id, "devices")
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    targets = [i for i in instances if i.get("enabled", True) and (not instance or i["id"] == instance)]
    last_error: Exception | None = None
    for inst in targets:
        try:
            detail = await service.get_device(site_id, inst["id"], device_id)
            detail["instance"] = inst["id"]
            return detail
        except (service.OpsError, Exception) as e:  # noqa: BLE001 - 逐实例尝试
            last_error = e
    if last_error:
        raise HTTPException(status_code=502, detail=str(last_error))
    raise HTTPException(status_code=404, detail=f"device not found: {device_id}")
