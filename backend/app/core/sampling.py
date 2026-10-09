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
    await push_samples([(resource_id, series, value)])


async def push_samples(items: list[tuple[str, str, float]]) -> None:
    """批量写采样（单次 pipeline），items: [(resource_id, series, value), ...]。

    get_queues 每队列 2 个序列、上百队列，逐条 await 会产生几百次往返。
    """
    if not items:
        return
    now = int(time.time())
    async with get_platform_redis().pipeline(transaction=True) as pipe:
        for resource_id, series, value in items:
            key = sample_key(resource_id, series)
            pipe.lpush(key, json.dumps({"ts": now, "v": value}))
            pipe.ltrim(key, 0, SAMPLE_MAX - 1)
            pipe.expire(key, 7200)  # 写入即续期：活跃序列常驻，孤儿序列末次推送 2h 后消亡
        await pipe.execute()


async def value_minutes_ago(resource_id: str, series: str, minutes: float = 5) -> float | None:
    """返回 >= minutes 前的最近一个采样值；无足够历史时 None。"""
    return (await values_minutes_ago([(resource_id, series)], minutes))[(resource_id, series)]


async def values_minutes_ago(items: list[tuple[str, str]], minutes: float = 5) -> dict[tuple[str, str], float | None]:
    """返回最接近 minutes 前的采样值：取 ts ∈ [now-minutes*90s, now-minutes*60s] 的
    最近一条。上限容差 1.5 倍窗口：采样稀疏时（如刚打开页面、序列刚建立）参考点
    可能是几分钟前的旧样本，直接做差会把"跨多分钟的增量"误报成分钟增量——
    宁可返回 None（前端显示 '-'）也不虚报。"""
    if not items:
        return {}
    now = time.time()
    cutoff = now - minutes * 60
    floor = now - minutes * 90
    async with get_platform_redis().pipeline(transaction=True) as pipe:
        for resource_id, series in items:
            pipe.lrange(sample_key(resource_id, series), 0, SAMPLE_MAX - 1)
        raw_list = await pipe.execute()
    out: dict[tuple[str, str], float | None] = {}
    for item, raw in zip(items, raw_list):
        found = None
        for entry in (json.loads(x) for x in raw):  # 新 -> 旧
            if entry["ts"] <= cutoff:
                found = entry["v"] if entry["ts"] >= floor else None
                break
        out[item] = found
    return out


async def read_series(resource_id: str, series: str, limit: int = 60) -> list[dict]:
    """读取采样序列（新 -> 旧）：[{ts, v}, ...]，供前端画趋势图。"""
    limit = min(max(1, limit), SAMPLE_MAX)
    raw = await get_platform_redis().lrange(sample_key(resource_id, series), 0, limit - 1)
    return [json.loads(x) for x in raw]
