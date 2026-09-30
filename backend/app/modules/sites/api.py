from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, create_model, field_validator, model_validator

from . import service

router = APIRouter(tags=["sites"])


class SiteIn(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    enabled: bool = True
    thresholds: dict[str, int] | None = None  # 站点级阈值覆盖（PRD §8.6）


class SiteUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    thresholds: dict[str, int] | None = None


# ---------- 资源配置模型（PRD §5.2 通用结构） ----------


class ResourceBase(BaseModel):
    id: str | None = None
    name: str
    enabled: bool = True


class ServerConfig(ResourceBase):
    host: str
    port: int = 22
    username: str  # 现场仅支持用户名+密码登录（必填）
    password: str  # 必填；明文存储，接口不回显
    thresholds: dict[str, int] | None = None  # 资源级阈值覆盖（PRD §8.6）


class RedisConfig(ResourceBase):
    host: str
    port: int = 6379
    username: str = ""
    password: str = ""  # 可空（无密码站点）；浏览页可切 DB，配置不绑定


class MqConfig(ResourceBase):
    host: str
    port: int = 61616
    username: str = ""
    password: str = ""


class DeviceCustomField(BaseModel):
    """Device 自定义展示字段：key 前端生成一次且稳定（cf_+5hex）；
    bind/template 语义与 field_map 相同（模板优先），value_map 为该字段
    独立的值->展示映射。轻校验：key 必填、展示名至少一种语言；
    未声明的字段在此被剥离（pydantic 默认忽略 extra）。
    校验放在本模型上（而非 DeviceConfig 的 field_validator），
    这样经 create_model 派生的 update 模型同样生效。"""

    key: str = Field(min_length=1)
    label_zh: str = ""
    label_en: str = ""
    bind: str | None = None
    template: str | None = None
    value_map: dict[str, str] | None = None

    @field_validator("label_zh", "label_en")
    @classmethod
    def _strip_label(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def _need_one_label(self) -> "DeviceCustomField":
        if not (self.label_zh or self.label_en):
            raise ValueError("custom field requires label_zh or label_en")
        return self


# ≤10 上限用 Annotated 约束表达（随注解复制到 update 模型，两路同样生效）
_MAX_CUSTOM_FIELDS = Field(max_length=10)


class DeviceConfig(ResourceBase):
    base_url: str  # 完整 API 地址（可含路径，如 http://host:19030/mission/robot/info/active——上游真实路径，保持原样）
    list_path: str = ""  # 留空 = 直接请求 base_url；地址与路径分离的场景才填（如 /mission/agent/list）
    username: str = ""
    password: str = ""
    # 实例级字段映射（业务字段 -> 上游字段名），应对不同环境响应结构差异。
    # 例：{"status": "runState", "battery": "power"}；未配置的字段走内置候选
    field_map: dict[str, str] | None = None
    # 实例级值->展示映射（枚举翻译），作用于字段映射后的最终值。
    # 例：{"status": {"1": "CREATE", "2": "Free"}}；每个实例独立，未命中显示原值
    value_map: dict[str, dict[str, str]] | None = None
    # 自定义展示字段（最多 10 个），产出在各项稳定 key 下
    custom_fields: Annotated[list[DeviceCustomField], _MAX_CUSTOM_FIELDS] | None = None


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
        "devices": DeviceConfig,
    }.items()
}


def _add_resource_routes(res_type: str, url_segment: str, create_model_cls: type, update_model_cls: type) -> None:
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

    router.get(f"/sites/{{site_id}}/{url_segment}")(list_resources)
    router.post(f"/sites/{{site_id}}/{url_segment}", status_code=201)(create_resource)
    router.get(f"/sites/{{site_id}}/{url_segment}/{{resource_id}}")(get_resource)
    router.put(f"/sites/{{site_id}}/{url_segment}/{{resource_id}}")(update_resource)
    router.delete(f"/sites/{{site_id}}/{url_segment}/{{resource_id}}", status_code=204)(delete_resource)


# device 实例配置的 URL 段让位给业务路由（/sites/{id}/devices = 设备列表），
# 仅 URL 不同，存储 key 与 res_type 仍是 "devices"（旧数据由 device 模块启动迁移）
URL_SEGMENT = {"devices": "device-instances"}


for _type, (_create, _update) in RESOURCE_MODELS.items():
    _add_resource_routes(_type, URL_SEGMENT.get(_type, _type), _create, _update)


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
