import mimetypes
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, create_model

from . import service

router = APIRouter(tags=["knowledge"])


class DocRename(BaseModel):
    """编辑仅改名（文件内容创建后不可变）。"""

    name: str
    description: str | None = None


# 全字段可选更新模型（Annotated metadata 随行，同 sites/_update_model 模式）
DocUpdate = create_model(
    "DocUpdate",
    **{
        n: (f.annotation | None if f.annotation is not str else str | None, None)
        for n, f in DocRename.model_fields.items()
    },
)


@router.get("/knowledge/{site_id}")
async def list_docs(site_id: str) -> list[dict]:
    try:
        return await service.list_docs(site_id)
    except service.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/knowledge/{site_id}", status_code=201)
async def create_doc(
    site_id: str,
    file: UploadFile,
    name: str = Form(""),
    description: str = Form(""),
) -> dict:
    """上传任意格式文件（≤1MB）。name 留空则取文件名去扩展名。"""
    content = await file.read()
    filename = (file.filename or "file").strip()
    mime = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    doc_name = name.strip() or filename.rsplit(".", 1)[0]
    try:
        return await service.create_doc(
            site_id,
            {"name": doc_name, "description": description.strip(), "filename": filename, "mime": mime},
            content,
        )
    except service.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except service.DuplicateDoc as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except service.FileTooLarge as e:
        raise HTTPException(status_code=413, detail=str(e)) from None


@router.get("/knowledge/{site_id}/{doc_id}/content")
async def get_content(site_id: str, doc_id: str) -> Response:
    """文件原始字节。inline + UTF-8 文件名：浏览器/pdf 阅读器可直接内嵌打开。"""
    try:
        doc = await service.get_doc(site_id, doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="doc not found")
        blob = await service.get_blob(site_id, doc_id)
    except service.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    if blob is None:
        raise HTTPException(status_code=404, detail="doc content not found")
    filename = doc.get("filename") or doc_id
    return Response(
        content=blob,
        media_type=doc.get("mime") or "application/octet-stream",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.put("/knowledge/{site_id}/{doc_id}")
async def update_doc(site_id: str, doc_id: str, data: DocUpdate) -> dict:
    try:
        item = await service.update_doc(site_id, doc_id, data.model_dump(exclude_unset=True))
    except service.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except service.DuplicateDoc as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    if item is None:
        raise HTTPException(status_code=404, detail="doc not found")
    return item


@router.delete("/knowledge/{site_id}/{doc_id}", status_code=204)
async def delete_doc(site_id: str, doc_id: str) -> None:
    try:
        deleted = await service.delete_doc(site_id, doc_id)
    except service.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    if not deleted:
        raise HTTPException(status_code=404, detail="doc not found")
