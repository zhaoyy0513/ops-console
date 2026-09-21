from fastapi import APIRouter

from backend.app.core import oplog

router = APIRouter(tags=["audit"])


@router.get("/audit")
async def audit(page: int = 1, size: int = 50) -> dict:
    """操作日志分页（PRD §17.2，无用户维度，全量 ≤1000 条）。"""
    page = max(1, page)
    size = min(max(1, size), 200)
    items, total = await oplog.read_page(page, size)
    return {"items": items, "total": total, "page": page, "size": size}
