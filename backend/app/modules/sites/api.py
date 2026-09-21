from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
