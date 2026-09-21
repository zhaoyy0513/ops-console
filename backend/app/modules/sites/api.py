from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, create_model

from . import service

router = APIRouter(tags=["sites"])


class SiteIn(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    enabled: bool = True


class SiteUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None


# ---------- 资源配置模型（PRD §5.2 通用结构） ----------


class ResourceBase(BaseModel):
    id: str | None = None
    name: str
    enabled: bool = True


class ServerConfig(ResourceBase):
    host: str
    port: int = 22
    username: str = ""
    password: str = ""
    private_key: str = ""  # SSH 私钥（可选，PRD §8.1）


class RedisConfig(ResourceBase):
    host: str
    port: int = 6379
    username: str = ""
    password: str = ""
    db: int = 0


class MqConfig(ResourceBase):
    host: str
    port: int = 8161
    username: str = ""
    password: str = ""


class RobotConfig(ResourceBase):
    base_url: str
    username: str = ""
    password: str = ""


def _update_model(model: type[BaseModel]) -> type[BaseModel]:
    """全字段可选的更新模型。"""
    return create_model(
        f"{model.__name__}Update",
        **{n: (f.annotation | None, None) for n, f in model.model_fields.items()},
    )


RESOURCE_MODELS: dict[str, tuple[type[BaseModel], type[BaseModel]]] = {
    res_type: (model, _update_model(model))
    for res_type, model in {
        "servers": ServerConfig,
        "redis": RedisConfig,
        "mq": MqConfig,
        "robots": RobotConfig,
    }.items()
}


def _add_resource_routes(res_type: str, create_model_cls: type, update_model_cls: type) -> None:
    def not_found(detail: str) -> HTTPException:
        return HTTPException(status_code=404, detail=detail)

    async def list_resources(site_id: str) -> list[dict]:
        try:
            return await service.list_resources(site_id, res_type)
        except service.NotFound as e:
            raise not_found(str(e)) from None

    async def create_resource(site_id: str, data: create_model_cls) -> dict:  # type: ignore[valid-type]
        try:
            return await service.create_resource(
                site_id, res_type, data.model_dump(exclude_none=True)
            )
        except service.NotFound as e:
            raise not_found(str(e)) from None
        except service.DuplicateResource as e:
            raise HTTPException(status_code=409, detail=str(e)) from None

    async def get_resource(site_id: str, resource_id: str) -> dict:
        item = await service.get_resource(site_id, res_type, resource_id)
        if item is None:
            raise not_found(f"resource not found: {resource_id}")
        return item

    async def update_resource(site_id: str, resource_id: str, data: update_model_cls) -> dict:  # type: ignore[valid-type]
        try:
            item = await service.update_resource(
                site_id, res_type, resource_id, data.model_dump(exclude_unset=True)
            )
        except service.NotFound as e:
            raise not_found(str(e)) from None
        if item is None:
            raise not_found(f"resource not found: {resource_id}")
        return item

    async def delete_resource(site_id: str, resource_id: str) -> None:
        try:
            deleted = await service.delete_resource(site_id, res_type, resource_id)
        except service.NotFound as e:
            raise not_found(str(e)) from None
        if not deleted:
            raise not_found(f"resource not found: {resource_id}")

    for fn in (list_resources, create_resource, get_resource, update_resource, delete_resource):
        fn.__name__ = f"{fn.__name__}_{res_type}"  # 避免重复 operation id

    router.get(f"/sites/{{site_id}}/{res_type}")(list_resources)
    router.post(f"/sites/{{site_id}}/{res_type}", status_code=201)(create_resource)
    router.get(f"/sites/{{site_id}}/{res_type}/{{resource_id}}")(get_resource)
    router.put(f"/sites/{{site_id}}/{res_type}/{{resource_id}}")(update_resource)
    router.delete(f"/sites/{{site_id}}/{res_type}/{{resource_id}}", status_code=204)(delete_resource)


for _type, (_create, _update) in RESOURCE_MODELS.items():
    _add_resource_routes(_type, _create, _update)


# ---------- 导出 / 导入 ----------


class ImportPayload(BaseModel):
    # extra=forbid：防止拼错的 payload 被当成"导入 0 个站点"而清空全部配置
    model_config = {"extra": "forbid"}

    version: int = 1
    exported_at: str | None = None
    sites: list[dict]


@router.post("/sites/export")
async def export_sites() -> dict:
    """全量导出（含密码，仅内部备份用途，PRD §6.3）。"""
    return await service.export_all()


@router.post("/sites/import")
async def import_sites(data: ImportPayload) -> dict:
    count = await service.import_all(data.sites)
    return {"imported": count}


# ---------- 站点 CRUD ----------


@router.get("/sites")
async def list_sites() -> list[dict]:
    return await service.list_sites()


@router.post("/sites", status_code=201)
async def create_site(data: SiteIn) -> dict:
    try:
        return await service.create_site(data.model_dump(exclude_none=True))
    except service.DuplicateSite as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


@router.get("/sites/{site_id}")
async def get_site(site_id: str) -> dict:
    site = await service.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"site not found: {site_id}")
    return site


@router.put("/sites/{site_id}")
async def update_site(site_id: str, data: SiteUpdate) -> dict:
    site = await service.update_site(site_id, data.model_dump(exclude_none=True))
    if not site:
        raise HTTPException(status_code=404, detail=f"site not found: {site_id}")
    return site


@router.delete("/sites/{site_id}", status_code=204)
async def delete_site(site_id: str) -> None:
    if not await service.delete_site(site_id):
        raise HTTPException(status_code=404, detail=f"site not found: {site_id}")
