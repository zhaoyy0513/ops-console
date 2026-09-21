from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.modules.redis import service
from backend.app.modules.sites.service import NotFound

router = APIRouter(tags=["redis"])


@router.get("/sites/{site_id}/redis/{redis_id}/info")
async def get_info(site_id: str, redis_id: str, db: int = 0) -> dict:
    try:
        return await service.get_info(site_id, redis_id, db)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.get("/sites/{site_id}/redis/{redis_id}/keys")
async def list_keys(
    site_id: str,
    redis_id: str,
    db: int = 0,
    pattern: str = "*",
    cursor: int = 0,
    count: int = 100,
    type: str | None = None,
) -> dict:
    try:
        return await service.list_keys(
            site_id, redis_id, db=db, pattern=pattern, cursor=cursor, count=count, key_type=type
        )
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except service.OpsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from None


@router.get("/sites/{site_id}/redis/{redis_id}/key")
async def get_key(site_id: str, redis_id: str, db: int = 0, key: str = "") -> dict:
    try:
        return await service.get_key(site_id, redis_id, db=db, key=key)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except service.OpsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from None


class OperationIn(BaseModel):
    op: Literal["set", "delete", "expire"]  # 白名单枚举，其余在实现层不可达（PRD §11.6）
    db: int = 0
    key: str
    type: Literal["string", "hash", "list", "set", "zset"] | None = None
    value: Any = None
    ttl: int | None = None  # expire：秒；负数 = PERSIST 清除过期


@router.post("/sites/{site_id}/redis/{redis_id}/operations")
async def operate(site_id: str, redis_id: str, body: OperationIn) -> dict:
    try:
        return await service.operate(
            site_id,
            redis_id,
            op=body.op,
            db=body.db,
            key=body.key,
            ktype=body.type,
            value=body.value,
            ttl=body.ttl,
        )
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except service.OpsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from None
