import json
import uuid
from datetime import datetime, timezone

from backend.app.core.redis import get_platform_redis

SITES_KEY = "ops:sites"  # Set: 全部站点 id（PRD §6.2）
RESOURCE_TYPES = ("servers", "redis", "mq", "robots")


def site_key(site_id: str) -> str:
    return f"ops:site:{site_id}"


def resource_key(site_id: str, res_type: str) -> str:
    """资源 Hash：field=resource_id, value=JSON 配置（PRD §6.2）。"""
    return f"ops:site:{site_id}:{res_type}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_site(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row.get("description", ""),
        "enabled": row.get("enabled") == "1",
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
        "created_at": now,
        "updated_at": now,
    }
    await r.hset(site_key(site_id), mapping=full)
    await r.sadd(SITES_KEY, site_id)
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
    row["updated_at"] = _now()
    await r.hset(key, mapping=row)
    return _row_to_site(row)


async def delete_site(site_id: str) -> bool:
    r = get_platform_redis()
    if not await r.hexists(site_key(site_id), "id"):
        return False
    keys = [site_key(site_id)] + [resource_key(site_id, t) for t in RESOURCE_TYPES]
    await r.delete(*keys)
    await r.srem(SITES_KEY, site_id)
    return True


# ---------- 资源配置（servers / redis / mq / robots，PRD §5.2） ----------


async def _require_site(site_id: str) -> None:
    if not await get_platform_redis().hexists(site_key(site_id), "id"):
        raise NotFound(f"site not found: {site_id}")


def _strip_password(config: dict) -> dict:
    """查询接口不回显密码（PRD §5.2）：返回空串。"""
    return {k: ("" if k == "password" else v) for k, v in config.items()}


async def list_resources(site_id: str, res_type: str) -> list[dict]:
    await _require_site(site_id)
    raw = await get_platform_redis().hvals(resource_key(site_id, res_type))
    return sorted((_strip_password(json.loads(x)) for x in raw), key=lambda c: c["id"])


async def get_resource(site_id: str, res_type: str, resource_id: str) -> dict | None:
    await _require_site(site_id)
    raw = await get_platform_redis().hget(resource_key(site_id, res_type), resource_id)
    return _strip_password(json.loads(raw)) if raw else None


async def create_resource(site_id: str, res_type: str, data: dict) -> dict:
    await _require_site(site_id)
    r = get_platform_redis()
    key = resource_key(site_id, res_type)
    resource_id = data.get("id") or uuid_hex()
    if await r.hexists(key, resource_id):
        raise DuplicateResource(resource_id)
    data = {**data, "id": resource_id}
    await r.hset(key, resource_id, json.dumps(data, ensure_ascii=False))
    return _strip_password(data)


async def update_resource(site_id: str, res_type: str, resource_id: str, data: dict) -> dict | None:
    await _require_site(site_id)
    r = get_platform_redis()
    key = resource_key(site_id, res_type)
    raw = await r.hget(key, resource_id)
    if not raw:
        return None
    old = json.loads(raw)
    # 密码留空/缺省 = 不修改（PRD §5.2）
    if not data.get("password"):
        data.pop("password", None)
    old.update(data)
    old["id"] = resource_id
    await r.hset(key, resource_id, json.dumps(old, ensure_ascii=False))
    return _strip_password(old)


async def delete_resource(site_id: str, res_type: str, resource_id: str) -> bool:
    await _require_site(site_id)
    deleted = await get_platform_redis().hdel(resource_key(site_id, res_type), resource_id)
    return deleted > 0


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
