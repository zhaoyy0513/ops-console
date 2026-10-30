import mimetypes

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, create_model

from . import service

router = APIRouter(tags=["knowledge"])

# 单文件上限，与 service.MAX_FILE_BYTES 同值（这里用于报错文案与文档注释）
MAX_MB = service.MAX_FILE_BYTES // (1024 * 1024)


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
    """上传任意格式文件（≤{max}MB，流式写盘不占后端内存）。
    name 留空则取文件名去扩展名；重名自动追加 -2 / -3。"""
    filename = (file.filename or "file").strip()
    mime = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    doc_name = name.strip() or filename.rsplit(".", 1)[0]

    # 客户端声称的大小先行拦截（省得上传 200MB 才收到 413）
    if file.size and file.size > service.MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"file exceeds {MAX_MB}MB limit")

    try:
        return await service.create_doc(
            site_id,
            {"name": doc_name, "description": description.strip(), "filename": filename, "mime": mime},
            await file.read(),
        )
    except service.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except service.DuplicateDoc as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except service.FileTooLarge as e:
        raise HTTPException(status_code=413, detail=str(e)) from None


@router.get("/knowledge/{site_id}/{doc_id}/content")
async def get_content(site_id: str, doc_id: str) -> Response:
    """文件字节。优先磁盘文件（FileResponse 流式）；旧版 Redis blob / markdown
    字段文档经 get_file 兼容读取（合成 text/markdown）。"""
    try:
        doc = await service.get_doc(site_id, doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="doc not found")
        filename = doc.get("filename") or ""

        # ① 新文档：磁盘流式返回
        f = service.storage_file(site_id, doc_id, filename)
        if f is not None:
            return FileResponse(
                path=f,
                media_type=doc.get("mime") or "application/octet-stream",
                headers={"Cache-Control": "private, max-age=300"},
            )

        # ② 历史文档（Redis blob / markdown 字段）：内存读出后回 Response
        got = await service.get_file(site_id, doc_id)
    except service.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    if got is None:
        raise HTTPException(status_code=404, detail="doc content not found")
    content, _ = got
    return Response(
        content=content,
        media_type=doc.get("mime") or "application/octet-stream",
        # 不带 Content-Disposition：带 filename 的 inline 头会被 IDM 等下载管理器当成下载任务拦截
        # （PDF 在预览时直接跳到本地下载器）。文件名由前端 <a download> 属性指定。
        headers={"Cache-Control": "private, max-age=300"},
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
