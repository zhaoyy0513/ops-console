from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.modules.sites.service import NotFound

from . import service

router = APIRouter(tags=["logs"])


class SourceIn(BaseModel):
    label: str
    path: str


class SourceUpdate(BaseModel):
    label: str | None = None
    path: str | None = None


@router.get("/logs/{site_id}")
async def list_sources(site_id: str) -> list[dict]:
    try:
        return await service.list_sources(site_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/logs/{site_id}", status_code=201)
async def create_source(site_id: str, data: SourceIn) -> dict:
    try:
        return await service.create_source(site_id, data.model_dump())
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except service.DuplicateLabel as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.put("/logs/{site_id}/{source_id}")
async def update_source(site_id: str, source_id: str, data: SourceUpdate) -> dict:
    try:
        item = await service.update_source(
            site_id, source_id, data.model_dump(exclude_unset=True))
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except service.DuplicateLabel as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    if item is None:
        raise HTTPException(status_code=404, detail=f"log source not found: {source_id}")
    return item


@router.delete("/logs/{site_id}/{source_id}", status_code=204)
async def delete_source(site_id: str, source_id: str) -> None:
    try:
        deleted = await service.delete_source(site_id, source_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    if not deleted:
        raise HTTPException(status_code=404, detail=f"log source not found: {source_id}")


@router.get("/logs/{site_id}/{source_id}/files")
async def list_files(site_id: str, source_id: str) -> dict:
    """列出日志源目录下的文件（只 stat，不读内容）。"""
    try:
        return await service.list_files(site_id, source_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.get("/logs/{site_id}/{source_id}/read")
async def read_source(
    site_id: str,
    source_id: str,
    file: str = Query("", max_length=255, description="目录下的文件名（单段，不含分隔符）"),
    mode: Literal["tail", "head", "offset", "search"] = "tail",
    offset: int = Query(0, ge=0),
    kw: str = Query("", max_length=200),
    lines: int = Query(200, ge=1, le=1000),
) -> dict:
    """按字节窗口读取（不做全文件检索）。probe 失败以 200 + error_code 返回，
    前端保留已加载内容；源/站点不存在才是 404。"""
    try:
        return await service.read_source(
            site_id, source_id, file=file, mode=mode, offset=offset, kw=kw, lines=lines)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
