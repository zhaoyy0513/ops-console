import json
import uuid
from datetime import datetime, timezone

from backend.app.core import oplog
from backend.app.core.redis import get_platform_redis

SITES_KEY = "ops:sites"  # Set: 全部站点 id（PRD §6.2）
RESOURCE_TYPES = ("servers", "redis", "mq", "devices")
# 删除站点时一并清理的附属 key：overview 健康 hash、ssh 脚本 hash（字面量直写，避免跨模块循环导入）
HEALTH_KEY = "ops:health:{site_id}"  # overview/service.py health_key 同格式
SSH_SCRIPTS_KEY = "ops:site:{site_id}:ssh_scripts"  # ssh/service.py _key 同格式


def site_key(site_id: str) -> str:
    return f"ops:site:{site_id}"


def resource_key(site_id: str, res_type: str) -> str:
    """资源 Hash：field=resource_id, value=JSON 配置（PRD §6.2）。"""
    return f"ops:site:{site_id}:{res_type}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_site(row: dict) -> dict:
    thresholds = json.loads(row["thresholds"]) if row.get("thresholds") else None
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row.get("description", ""),
        "enabled": row.get("enabled") == "1",
        "thresholds": thresholds,
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


async def create_site(data: dict) -> dict:
    r = get_platform_redis()
    site_id = data.get("id")
    if not site_id:
        site_id = uuid_hex()
    if await r.hexists(site_key(site_id), "id"):
        raise DuplicateSite(site_id)

    now = _now()
    full = {
        "id": site_id,
        "name": data["name"],
        "description": data.get("description", ""),
        "enabled": "1" if data.get("enabled", True) else "0",
        "thresholds": json.dumps(data["thresholds"]) if data.get("thresholds") else "",
        "created_at": now,
        "updated_at": now,
    }
    await r.hset(site_key(site_id), mapping=full)
    await r.sadd(SITES_KEY, site_id)
    await oplog.record(site_id, "site-config", "SITE_CREATED",
                       target=data["name"], params={"site_id": site_id})
    return _row_to_site(full)


async def get_site(site_id: str) -> dict | None:
    row = await get_platform_redis().hgetall(site_key(site_id))
    return _row_to_site(row) if row else None


async def list_sites() -> list[dict]:
    r = get_platform_redis()
    ids = sorted(await r.smembers(SITES_KEY))
    sites = []
    for sid in ids:
        site = await get_site(sid)
        if site:
            sites.append(site)
    return sites


async def update_site(site_id: str, data: dict) -> dict | None:
    r = get_platform_redis()
    key = site_key(site_id)
    row = await r.hgetall(key)
    if not row:
        return None
    row["name"] = data.get("name", row["name"])
    row["description"] = data.get("description", row.get("description", ""))
    row["enabled"] = ("1" if data["enabled"] else "0") if "enabled" in data else row["enabled"]
    if "thresholds" in data:
        row["thresholds"] = json.dumps(data["thresholds"]) if data["thresholds"] else ""
    row["updated_at"] = _now()
    await r.hset(key, mapping=row)
    await oplog.record(site_id, "site-config", "SITE_UPDATED",
                       target=row["name"], params={"site_id": site_id})
    return _row_to_site(row)


async def delete_site(site_id: str) -> bool:
    r = get_platform_redis()
    row = await r.hgetall(site_key(site_id))
    if not row:
        return False
    # 定时脚本随站点删除：先停调度再删配置（晚了 hash 没了就找不到 job，cron 泄漏）
    from backend.app.modules.ssh import scheduling  # 延迟导入避免循环依赖

    for script_id in await r.hkeys(SSH_SCRIPTS_KEY.format(site_id=site_id)):
        scheduling.unschedule(site_id, script_id)
    keys = [site_key(site_id), SSH_SCRIPTS_KEY.format(site_id=site_id),
            HEALTH_KEY.format(site_id=site_id)]
    keys += [resource_key(site_id, t) for t in RESOURCE_TYPES]
    await r.delete(*keys)
    await r.srem(SITES_KEY, site_id)
    await oplog.record(site_id, "site-config", "SITE_DELETED",
                       target=row.get("name") or site_id, params={"site_id": site_id})
    return True


# ---------- 资源配置（servers / redis / mq / devices，PRD §5.2） ----------
# 决策记录（2026-09-22，用户指令）：内部工具全明文——查询接口返回明文密码，
# 推翻 PRD §5.2 的"密码不回显"要求；更新语义为"提交什么存什么"。


async def _require_site(site_id: str) -> None:
    if not await get_platform_redis().hexists(site_key(site_id), "id"):
        raise NotFound(f"site not found: {site_id}")


async def list_resources(site_id: str, res_type: str, include_password: bool = True) -> list[dict]:
    await _require_site(site_id)
    raw = await get_platform_redis().hvals(resource_key(site_id, res_type))
    items = [json.loads(x) for x in raw]
    if not include_password:
        # ponytail: 兼容旧签名；当前全部调用方都用明文
        items = [{k: ("" if k == "password" else v) for k, v in c.items()} for c in items]
    return sorted(items, key=lambda c: c["id"])


async def get_resource_raw(site_id: str, res_type: str, resource_id: str) -> dict | None:
    """读原始配置（含密码）。供各资源模块 provider 建连与前端展示共用。"""
    await _require_site(site_id)
    raw = await get_platform_redis().hget(resource_key(site_id, res_type), resource_id)
    return json.loads(raw) if raw else None


async def get_resource(site_id: str, res_type: str, resource_id: str) -> dict | None:
    return await get_resource_raw(site_id, res_type, resource_id)


def _res_label(data: dict, resource_id: str) -> str:
    """oplog 展示用资源名：name 优先，缺省退回 id（内部 id 一律只进 params）。"""
    return str(data.get("name") or resource_id)


async def create_resource(site_id: str, res_type: str, data: dict) -> dict:
    await _require_site(site_id)
    r = get_platform_redis()
    key = resource_key(site_id, res_type)
    resource_id = data.get("id") or uuid_hex()
    if await r.hexists(key, resource_id):
        raise DuplicateResource(resource_id)
    data = {**data, "id": resource_id}
    await r.hset(key, resource_id, json.dumps(data, ensure_ascii=False))
    name = _res_label(data, resource_id)
    await oplog.record(site_id, f"{res_type}/{name}", "RESOURCE_CONFIG_CREATED",
                       target=name, params={"resource_id": resource_id})
    return data


async def update_resource(site_id: str, res_type: str, resource_id: str, data: dict) -> dict | None:
    await _require_site(site_id)
    r = get_platform_redis()
    key = resource_key(site_id, res_type)
    raw = await r.hget(key, resource_id)
    if not raw:
        return None
    old = json.loads(raw)
    # 提交什么存什么（exclude_unset 只带显式提交的字段）；明文策略下编辑即覆盖
    old.update(data)
    old["id"] = resource_id
    await r.hset(key, resource_id, json.dumps(old, ensure_ascii=False))
    name = _res_label(old, resource_id)
    await oplog.record(site_id, f"{res_type}/{name}", "RESOURCE_CONFIG_UPDATED",
                       target=name, params={"resource_id": resource_id})
    return old


async def delete_resource(site_id: str, res_type: str, resource_id: str) -> bool:
    await _require_site(site_id)
    r = get_platform_redis()
    key = resource_key(site_id, res_type)
    raw = await r.hget(key, resource_id)
    if not raw:
        return False
    name = _res_label(json.loads(raw), resource_id)
    await r.hdel(key, resource_id)
    await oplog.record(site_id, f"{res_type}/{name}", "RESOURCE_CONFIG_DELETED",
                       target=name, params={"resource_id": resource_id})
    return True


class NotFound(Exception):
    pass


class DuplicateResource(Exception):
    def __init__(self, resource_id: str):
        super().__init__(f"resource already exists: {resource_id}")
        self.resource_id = resource_id


class DuplicateSite(Exception):
    def __init__(self, site_id: str):
        super().__init__(f"site already exists: {site_id}")
        self.site_id = site_id


def uuid_hex() -> str:
    return uuid.uuid4().hex[:8]


# ---------- 导出 / 导入（PRD §6.3） ----------


async def export_all() -> dict:
    """全量导出（含密码——导入后需可直接连通，仅限内部备份用途）。"""
    sites = []
    for site in await list_sites():
        sid = site["id"]
        site = dict(site)
        for t in RESOURCE_TYPES:
            site[t] = await list_resources(sid, t, include_password=True)
        sites.append(site)
    return {"version": 1, "exported_at": _now(), "sites": sites}


async def import_all(sites: list[dict]) -> int:
    """覆盖式导入：清空现有配置后按导出格式重建。"""
    r = get_platform_redis()
    old_ids = list(await r.smembers(SITES_KEY))
    if old_ids:
        keys: list[str] = [site_key(s) for s in old_ids]
        keys += [resource_key(s, t) for s in old_ids for t in RESOURCE_TYPES]
        await r.delete(*keys)
        await r.srem(SITES_KEY, *old_ids)

    for s in sites:
        resources = {t: s.pop(t, []) for t in RESOURCE_TYPES}
        await create_site(s)
        sid = s["id"]
        for t, items in resources.items():
            for item in items:
                await r.hset(resource_key(sid, t), item["id"], json.dumps(item, ensure_ascii=False))

    await oplog.record("-", "site-config", "IMPORT_CONFIG", params={"sites": len(sites)})
    return len(sites)
