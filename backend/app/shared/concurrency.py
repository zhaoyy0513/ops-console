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


_host_semaphores: dict[str, asyncio.Semaphore] = {}


def get_host_semaphore(host: str, limit: int = 2) -> asyncio.Semaphore:
    """按目标主机限流：脚本/流式执行专用。

    全局类型信号量只限总并发，挡不住「N 个用户同时打同一台服务器」——
    按主机再加一层（默认 2），目标机的子进程堆积才有上界。
    字典按主机名增长、数量以站点资源数为上界，无需清理。
    """
    key = f"host:{host}"
    if key not in _host_semaphores:
        _host_semaphores[key] = asyncio.Semaphore(limit)
    return _host_semaphores[key]
