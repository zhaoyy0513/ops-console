"""TCP 连通性探测：目标解析 + 3s 超时 + 最多 10 并发。

探测从后端出站，不需要目标机权限；单个目标失败只影响该行。
"""

import asyncio
import time
from urllib.parse import urlsplit

# 各资源类型未显式配置端口时的默认值（devices 由 base_url 的 scheme 决定）
DEFAULT_PORTS = {"servers": 22, "redis": 6379, "mq": 61616}
PROBE_TIMEOUT = 3.0
MAX_CONCURRENCY = 10


def parse_base_url(base_url: str) -> tuple[str, int] | None:
    """base_url → (host, port)。覆盖 http/https、带路径、无端口、缺 scheme。

    scheme 为 https 时默认 443，其余（含无 scheme）默认 80；
    host 为空或端口非数字返回 None（该行按不可达处理，不拖垮整批）。
    """
    raw = (base_url or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "//" + raw  # 无 scheme 时按 netloc 解析，避免 "host:port" 被当成 scheme
    try:
        parts = urlsplit(raw)
        host = parts.hostname
        port = parts.port
    except ValueError:  # 非法端口（如 :abc / 越界）
        return None
    if not host:
        return None
    return host, port or (443 if parts.scheme == "https" else 80)


def target_of(resource_type: str, cfg: dict) -> tuple[str, int] | None:
    """资源配置 → (host, port)；缺 host 或端口非法返回 None。"""
    if resource_type == "devices":
        return parse_base_url(str(cfg.get("base_url") or ""))
    host = str(cfg.get("host") or "").strip()
    if not host:
        return None
    try:
        port = int(cfg.get("port") or DEFAULT_PORTS.get(resource_type, 0))
    except (TypeError, ValueError):
        return None
    return (host, port) if port > 0 else None


async def probe(host: str, port: int, timeout: float = PROBE_TIMEOUT) -> dict:
    """单目标 TCP 连接探测，返回 {ok, latency_ms, error}。"""
    started = time.perf_counter()
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout
        )
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass  # 对端已断不影响「连上了」这一事实
        return {"ok": True, "latency_ms": _elapsed_ms(started), "error": None}
    except TimeoutError:
        return {"ok": False, "latency_ms": _elapsed_ms(started), "error": "timeout"}
    except OSError as e:  # 拒绝连接 / DNS 失败 / 网络不可达
        return {
            "ok": False,
            "latency_ms": _elapsed_ms(started),
            "error": e.strerror or str(e) or type(e).__name__,
        }


async def probe_all(
    targets: list[dict],
    *,
    concurrency: int = MAX_CONCURRENCY,
    timeout: float = PROBE_TIMEOUT,
) -> list[dict]:
    """并发探测全部目标（Semaphore 限流），结果与输入顺序一一对应。"""
    sem = asyncio.Semaphore(concurrency)

    async def one(t: dict) -> dict:
        async with sem:
            return await probe(t["host"], t["port"], timeout)

    return list(await asyncio.gather(*(one(t) for t in targets)))


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
