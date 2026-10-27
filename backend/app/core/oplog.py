import json
from datetime import datetime, timezone

from .redis import get_platform_redis
from .request_info import get_caller

OPLOG_KEY = "ops:oplog"
OPLOG_MAX = 320  # 只保留最近 320 条（原 1000 → 200 → 320，操作日志页 16 页 × 16 行）


async def record(
    site: str,
    resource: str,
    operation: str,
    *,
    target: str | None = None,
    params: dict | None = None,
    result: str = "SUCCESS",
    error: str | None = None,
) -> None:
    """记录一条操作日志（无用户维度，PRD §17）。

    字段约定（2026-09-29 统一，修复"日志缺关键信息"）：
    - target   = 操作对象的人类可读标识（redis key、脚本名、站点/资源名、pid+command）；
    - resource = 模块/实例名（如 redis/{实例name}、ssh/{server名}）——不放内部 id；
    - params   = 上下文（instance_id / host / db / …），不含大值或敏感值（如 redis value）。

    LPUSH + LTRIM 在同一事务管道内执行，超出 OPLOG_MAX 即淘汰旧日志。
    """
    caller, caller_ip = get_caller()
    entry = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "site": site,
        "resource": resource,
        "operation": operation,
        "target": target,
        "params": params,
        "result": result,
        "error": error,
        # 调用者溯源（2026-10-23）：IP 来自转发头解析，操作人别名由前端 localStorage
        # 设置并随 X-Ops-User 头携带；定时任务等无 HTTP 上下文路径为 "-"
        "caller": caller,
        "caller_ip": caller_ip,
    }
    async with get_platform_redis().pipeline(transaction=True) as pipe:
        pipe.lpush(OPLOG_KEY, json.dumps(entry, ensure_ascii=False))
        pipe.ltrim(OPLOG_KEY, 0, OPLOG_MAX - 1)
        await pipe.execute()


async def read_recent(n: int = 20) -> list[dict]:
    """最近 n 条（新→旧），Overview「最近操作」用。"""
    raw = await get_platform_redis().lrange(OPLOG_KEY, 0, n - 1)
    return [json.loads(x) for x in raw]


async def read_page(page: int = 1, size: int = 50, q: str = "") -> tuple[list[dict], int]:
    """分页读全量（新→旧），返回 (条目, 总数)，操作日志页面用。

    q 非空时对整条 JSON（含 cmd/target/operation/caller 等）做大小写不敏感的
    子串过滤——"查谁执行过 rm -rf" 直接搜 "rm -rf" 即可命中（含 BLOCKED 记录）。
    过滤在分页前做：命中集整体算 total，翻页在命中集内进行。"""
    r = get_platform_redis()
    if q.strip():
        needle = q.strip().lower()
        raw_all = await r.lrange(OPLOG_KEY, 0, -1)
        hits = [x for x in raw_all if needle in x.lower()]
        total = len(hits)
        start = (page - 1) * size
        return [json.loads(x) for x in hits[start:start + size]], total
    total = await r.llen(OPLOG_KEY)
    start = max(0, (page - 1) * size)
    raw = await r.lrange(OPLOG_KEY, start, start + size - 1)
    return [json.loads(x) for x in raw], total
