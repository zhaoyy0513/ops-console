from collections.abc import Awaitable, Callable

from backend.app.shared.errors import OpsError

# 资源类型 -> async tester(config) -> {success, latency_ms, message}
# 各模块 provider 在 register_module 时注册自己的 tester（T12/T16/T21/T24）。
TestFn = Callable[[dict], Awaitable[dict]]
_testers: dict[str, TestFn] = {}


def register_tester(resource_type: str, tester: TestFn) -> None:
    _testers[resource_type] = tester


async def test_connection(resource_type: str, config: dict) -> dict:
    tester = _testers.get(resource_type)
    if tester is None:
        raise OpsError(
            "UNKNOWN_RESOURCE_TYPE",
            f"no connection tester for type: {resource_type}",
            status_code=400,
        )
    return await tester(config)
