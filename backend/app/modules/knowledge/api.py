from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import AfterValidator, BaseModel, Field, create_model, model_validator

from . import service

router = APIRouter(tags=["knowledge"])

_MD_MAX = 1_000_000


def _normalize_markdown(v: str | None) -> str | None:
    """空白串归一为 None（AfterValidator 放 Annotated 元数据，随 _doc_update_model
    的 metadata 复制进入编辑路径——sites/_update_model 同款机制）。"""
    return v if v is not None and v.strip() else None


class DocIn(BaseModel):
    name: str
    description: str = ""
    # 1M 字符上限放 Annotated 元数据（同 sites._update_model 模式），创建/编辑双路径生效
    markdown: Annotated[str | None, Field(max_length=_MD_MAX), AfterValidator(_normalize_markdown)] = None
    enabled: bool = True

    @model_validator(mode="after")
    def _need_markdown(self) -> "DocIn":
        if not self.markdown:
            raise ValueError("doc requires markdown content")
        return self


# 全字段可选的更新模型（Annotated metadata 随行，1M 上限/空白归一双路径生效）。
# 刻意省略 `| None`：编辑多为仅改名场景，显式 null 的 markdown 会在 service 层
# 被剔除而非静默清正文；enabled 显式 null 会被 bool 校验拒为 422。
DocUpdate = create_model(
    "DocUpdate",
    **{
        n: (Annotated[f.annotation, *f.metadata] if f.metadata else f.annotation, None)
        for n, f in DocIn.model_fields.items()
    },
)


@router.get("/knowledge/{site_id}")
async def list_docs(site_id: str) -> list[dict]:
    try:
        return await service.list_docs(site_id)
    except service.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/knowledge/{site_id}", status_code=201)
async def create_doc(site_id: str, data: DocIn) -> dict:
    try:
        return await service.create_doc(site_id, data.model_dump(exclude_none=True))
    except service.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except service.DuplicateDoc as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


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
