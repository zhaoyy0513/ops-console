"""矩阵组装：读站点已配置资源 → 解析目标 → 并发探测。

只读调用 sites.service.list_resources；站点不存在时转成本模块的 NotFound（API 404）。
"""

from backend.app.modules.sites.service import NotFound as SiteNotFound
from backend.app.modules.sites.service import list_resources

from . import provider

RESOURCE_TYPES = ("servers", "redis", "mq", "devices")


class NotFound(Exception):
    pass


async def matrix(site_id: str) -> list[dict]:
    rows: list[dict] = []
    pending: list[tuple[dict, tuple[str, int]]] = []

    for res_type in RESOURCE_TYPES:
        try:
            cfgs = await list_resources(site_id, res_type)
        except SiteNotFound as e:
            raise NotFound(str(e)) from None
        for cfg in cfgs:
            target = provider.target_of(res_type, cfg)
            row = {
                "resource_type": res_type,
                "resource_name": str(cfg.get("name") or cfg.get("id") or ""),
                "host": target[0] if target else "",
                "port": target[1] if target else None,
                "ok": False,
                "latency_ms": 0,
                "error": "invalid host/base_url",
            }
            rows.append(row)
            if target:
                pending.append((row, target))

    results = await provider.probe_all(
        [{"host": host, "port": port} for _, (host, port) in pending]
    )
    for (row, _), result in zip(pending, results):
        row.update(result)
    return rows
