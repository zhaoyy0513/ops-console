from fastapi import APIRouter

from backend.app.core import oplog

router = APIRouter(tags=["audit"])


@router.get("/audit")
async def audit(page: int = 1, size: int = 50, q: str = "") -> dict:
    """操作日志分页（PRD §17.2）。q 非空时按关键词过滤（大小写不敏感子串，
    覆盖 cmd/target/operation/caller 等全部字段），用于"搜谁执行过 rm -rf"。"""
    page = max(1, page)
    size = min(max(1, size), 200)
    items, total = await oplog.read_page(page, size, q=q)
    return {"items": items, "total": total, "page": page, "size": size}
