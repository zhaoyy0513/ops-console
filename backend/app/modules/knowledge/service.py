import json
import uuid

from backend.app.core import oplog
from backend.app.core.redis import get_platform_redis
from backend.app.modules.sites.service import site_key


def knowledge_key(site_id: str) -> str:
    """知识库文档 Hash：field=doc_id, value=JSON（独立于 sites 资源存储）。"""
    return f"ops:knowledge:{site_id}"


async def _require_site(site_id: str) -> None:
    if not await get_platform_redis().hexists(site_key(site_id), "id"):
        raise NotFound(f"site not found: {site_id}")


async def list_docs(site_id: str) -> list[dict]:
    await _require_site(site_id)
    items = [json.loads(x) for x in await get_platform_redis().hvals(knowledge_key(site_id))]
    return sorted(items, key=lambda d: d["id"])


async def get_doc(site_id: str, doc_id: str) -> dict | None:
    await _require_site(site_id)
    raw = await get_platform_redis().hget(knowledge_key(site_id), doc_id)
    return json.loads(raw) if raw else None


async def create_doc(site_id: str, data: dict) -> dict:
    await _require_site(site_id)
    r = get_platform_redis()
    key = knowledge_key(site_id)
    doc_id = uuid.uuid4().hex[:8]  # id 由服务端生成（DocIn 无 id 字段，API 恒走此分支）
    name = str(data.get("name") or "").strip()
    await _check_name_unique(r, key, name)
    stored = {**{k: v for k, v in data.items() if k != "id"}, "id": doc_id}
    await r.hset(key, doc_id, json.dumps(stored, ensure_ascii=False))
    await oplog.record(site_id, f"knowledge/{name}", "KNOWLEDGE_CREATED",
                       target=name, params={"doc_id": doc_id})
    return stored


async def update_doc(site_id: str, doc_id: str, data: dict) -> dict | None:
    await _require_site(site_id)
    r = get_platform_redis()
    key = knowledge_key(site_id)
    raw = await r.hget(key, doc_id)
    if not raw:
        return None
    old = json.loads(raw)
    if "name" in data:
        await _check_name_unique(r, key, str(data.get("name") or "").strip(), exclude_id=doc_id)
    # 显式 null/空白的 markdown 不静默清正文（创建路径拒空白，编辑同口径；真要清空走删除重建）
    data = {k: v for k, v in data.items() if not (k == "markdown" and v is None)}
    old.update(data)
    old["id"] = doc_id
    await r.hset(key, doc_id, json.dumps(old, ensure_ascii=False))
    await oplog.record(site_id, f"knowledge/{old['name']}", "KNOWLEDGE_UPDATED",
                       target=old["name"], params={"doc_id": doc_id})
    return old


async def delete_doc(site_id: str, doc_id: str) -> bool:
    await _require_site(site_id)
    r = get_platform_redis()
    key = knowledge_key(site_id)
    raw = await r.hget(key, doc_id)
    if not raw:
        return False
    name = str(json.loads(raw).get("name") or doc_id)
    await r.hdel(key, doc_id)
    await oplog.record(site_id, f"knowledge/{name}", "KNOWLEDGE_DELETED",
                       target=name, params={"doc_id": doc_id})
    return True


async def _check_name_unique(r, key: str, name: str, exclude_id: str | None = None) -> None:
    if not name:
        return
    for rid, raw in (await r.hgetall(key)).items():
        if rid != exclude_id and json.loads(raw).get("name") == name:
            raise DuplicateDoc(f"name already in use: {name}")


class NotFound(Exception):
    pass


class DuplicateDoc(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)
