import asyncio
from collections.abc import Awaitable

from .errors import OpsError


async def with_timeout(
    coro: Awaitable,
    seconds: float,
    *,
    error_code: str = "REMOTE_TIMEOUT",
    message: str = "Operation timed out",
    resource: str | None = None,
):
    """统一超时策略：超时转为 OpsError，避免请求挂死（PRD §26）。"""
    try:
        return await asyncio.wait_for(coro, seconds)
    except TimeoutError:
        raise OpsError(error_code, message, resource) from None
