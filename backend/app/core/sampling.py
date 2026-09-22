"""短期指标采样：Redis List 保存 (ts, value)，供趋势对比（PRD §9.6）。

第一版不建时序库——够 queue backlog 趋势和 commands/sec 这类短窗对比。
"""

import time
import json

from .redis import get_platform_redis

SAMPLE_MAX = 100  # 每序列最多 100 个点（3s 轮询采样 ≈ 5 分钟窗口）


def sample_key(resource_id: str, series: str) -> str:
    return f"ops:sample:{resource_id}:{series}"


async def push_sample(resource_id: str, series: str, value: float) -> None:
    entry = json.dumps({"ts": int(time.time()), "v": value})
    async with get_platform_redis().pipeline(transaction=True) as pipe:
        pipe.lpush(sample_key(resource_id, series), entry)
        pipe.ltrim(sample_key(resource_id, series), 0, SAMPLE_MAX - 1)
        await pipe.execute()


async def value_minutes_ago(resource_id: str, series: str, minutes: float = 5) -> float | None:
    """返回 >= minutes 前的最近一个采样值；无足够历史时 None。"""
    cutoff = time.time() - minutes * 60
    raw = await get_platform_redis().lrange(sample_key(resource_id, series), 0, SAMPLE_MAX - 1)
    for entry in (json.loads(x) for x in raw):  # 新 -> 旧
        if entry["ts"] <= cutoff:
            return entry["v"]
    return None


async def read_series(resource_id: str, series: str, limit: int = 60) -> list[dict]:
    """读取采样序列（新 -> 旧）：[{ts, v}, ...]，供前端画趋势图。"""
    limit = min(max(1, limit), SAMPLE_MAX)
    raw = await get_platform_redis().lrange(sample_key(resource_id, series), 0, limit - 1)
    return [json.loads(x) for x in raw]
