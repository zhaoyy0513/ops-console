import json
from datetime import datetime, timezone

from .redis import get_platform_redis
from .request_info import get_caller

OPLOG_KEY = "ops:oplog"
OPLOG_MAX = 160  # 只保留最近 160 条（原 1000 → 200 → 320 → 160，操作日志页 10 页 × 16 行）

_MISSING = object()


def diff(before: dict, after: dict) -> tuple[dict, dict]:
    """配置变更差异：只返回发生变化的键（oplog 上限 160 条，不存全量配置）。"""
    keys = sorted({**before, **after})
    changed = [k for k in keys if before.get(k, _MISSING) != after.get(k, _MISSING)]
    return (
        {k: before[k] for k in changed if k in before},
        {k: after[k] for k in changed if k in after},
    )


def _mask(snapshot: dict | None) -> dict | None:
    """敏感字段脱敏：键名含 password 的值一律 "***"（has_password 这类布尔保持原样）。"""
    if not snapshot:
        return None
    return {
        k: "***" if "password" in k.lower() and not isinstance(v, bool) else v
        for k, v in snapshot.items()
    }


async def record(
    site: str,
    resource: str,
    operation: str,
    *,
    target: str | None = None,
    params: dict | None = None,
    result: str = "SUCCESS",
    error: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """记录一条操作日志（无用户维度，PRD §17）。

    字段约定（2026-09-29 统一，修复"日志缺关键信息"）：
    - target   = 操作对象的人类可读标识（redis key、脚本名、站点/资源名、pid+command）；
    - resource = 模块/实例名（如 redis/{实例name}、ssh/{server名}）——不放内部 id；
    - params   = 上下文（instance_id / host / db / …），不含大值或敏感值（如 redis value）。

    before/after（P0-7）：配置变更前后的**差异键**（配合 diff()），敏感值已脱敏；
    新建只有 after、删除只有 before。两者都空时不写这两个字段——老记录同样没有，
    读取端按"无差异信息"处理（向后兼容）。

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
    if before or after:
        entry["before"] = _mask(before)
        entry["after"] = _mask(after)
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
