import asyncio

import pytest

from backend.app.shared.errors import OpsError
from backend.app.shared.retry import with_retry


async def test_retries_connection_error_then_succeeds():
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OpsError("REMOTE_CONNECTION_FAILED", "down")
        return "ok"

    wrapped = with_retry(flaky)
    assert await wrapped() == "ok"
    assert calls == 2


async def test_no_retry_for_non_retryable():
    calls = 0

    async def auth_fail():
        nonlocal calls
        calls += 1
        raise OpsError("AUTH_FAILED", "bad creds")

    with pytest.raises(OpsError):
        await with_retry(auth_fail)()
    assert calls == 1  # 鉴权失败不重试


async def test_raises_after_exhausting_attempts():
    calls = 0

    async def always_down():
        nonlocal calls
        calls += 1
        raise OpsError("REMOTE_TIMEOUT", "timeout")

    with pytest.raises(OpsError):
        await with_retry(always_down, attempts=2, delay=0)()
    assert calls == 2  # 最多 1-2 次（PRD §26）
