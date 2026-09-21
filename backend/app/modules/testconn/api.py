import time

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.shared import testconn
from backend.app.shared.errors import OpsError

router = APIRouter(tags=["connection-test"])


class TestConnectionIn(BaseModel):
    type: str
    config: dict = {}


@router.post("/test-connection")
async def test_connection(body: TestConnectionIn) -> dict:
    """保存前连接测试（PRD §13）：失败不抛 HTTP 错误，返回 success=false 供前端展示。"""
    start = time.perf_counter()
    try:
        return await testconn.test_connection(body.type, body.config)
    except OpsError as e:
        if e.status_code < 500:
            raise  # 客户端错误（如未知类型）交由统一错误包络返回
        return {
            "success": False,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "message": e.message,
        }
