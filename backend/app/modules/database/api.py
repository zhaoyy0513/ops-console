from fastapi import APIRouter

# ponytail: 验收 18 的机制验证 stub，V2 实现 PostgreSQL/MySQL provider 时替换
router = APIRouter(tags=["database-demo"])


@router.get("/sites/{site_id}/database/demo")
async def demo_metrics() -> dict:
    return {"module": "database", "status": "DEMO", "metrics": {"connections": 0, "size_mb": 0}}
