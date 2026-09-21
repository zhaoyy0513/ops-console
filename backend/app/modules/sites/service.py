import uuid
from datetime import datetime, timezone

from backend.app.core.redis import get_platform_redis

SITES_KEY = "ops:sites"  # Set: 全部站点 id（PRD §6.2）


def site_key(site_id: str) -> str:
    return f"ops:site:{site_id}"


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
    await r.delete(site_key(site_id))
    await r.srem(SITES_KEY, site_id)
    return True


class DuplicateSite(Exception):
    def __init__(self, site_id: str):
        super().__init__(f"site already exists: {site_id}")
        self.site_id = site_id


def uuid_hex() -> str:
    return uuid.uuid4().hex[:8]
