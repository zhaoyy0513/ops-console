import asyncio

# ponytail: 单进程信号量，V1 单实例部署够用；多实例部署时换 Redis 信号量
_DEFAULT_LIMIT = 8
_semaphores: dict[str, asyncio.Semaphore] = {}


def get_semaphore(resource_type: str, limit: int = _DEFAULT_LIMIT) -> asyncio.Semaphore:
    """每类外部资源一个信号量，限制对外并发（PRD §27）。

    用法：async with get_semaphore("ssh"): ...
    """
    if resource_type not in _semaphores:
        _semaphores[resource_type] = asyncio.Semaphore(limit)
    return _semaphores[resource_type]
