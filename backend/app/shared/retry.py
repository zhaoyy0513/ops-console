"""连接类错误的有限重试（PRD §26）：最多 1-2 次，失败返回 UNKNOWN/ERROR。

只重试 REMOTE_CONNECTION_FAILED / REMOTE_TIMEOUT；参数错误、鉴权失败、
远端坏响应不重试。写操作（Redis operations）不套用——避免非幂等风险与重试风暴。
"""

import asyncio
from collections.abc import Awaitable, Callable

from .errors import OpsError

RETRYABLE_CODES = {"REMOTE_CONNECTION_FAILED", "REMOTE_TIMEOUT"}


def with_retry(fn: Callable[[], Awaitable], attempts: int = 2, delay: float = 0.5) -> Callable[[], Awaitable]:
    """返回包装后的 callable：连接类错误重试 attempts-1 次。"""

    async def wrapper():
        for i in range(attempts):
            try:
                return await fn()
            except OpsError as e:
                if e.error_code not in RETRYABLE_CODES or i >= attempts - 1:
                    raise
                await asyncio.sleep(delay)

    return wrapper
