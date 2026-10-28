import base64
import json
import uuid
from datetime import datetime, timezone

from backend.app.core import oplog
from backend.app.core.redis import get_platform_redis
from backend.app.modules.sites.service import site_key

# 单文件上限 1MB（原始字节；落 Redis 时 base64 编码，实际占约 1.33MB）
MAX_FILE_BYTES = 1_000_000


def knowledge_key(site_id: str) -> str:
    """知识库文档 Hash：field=doc_id, value=JSON 元数据（不含文件内容）。"""
    return f"ops:knowledge:{site_id}"


def blob_key(site_id: str, doc_id: str) -> str:
    """文件内容独立 key：元数据与内容分离，列表接口不必读出整份文件。
    内容以 base64 文本存——平台 Redis 单例固定 decode_responses=True（全局约定），
    二进制会被强行 utf-8 解码；base64 是唯一不动该契约的存法（体积 +33%）。"""
    return f"ops:knowledge:{site_id}:blob:{doc_id}"


async def _require_site(site_id: str) -> None:
    if not await get_platform_redis().hexists(site_key(site_id), "id"):
        raise NotFound(f"site not found: {site_id}")


async def list_docs(site_id: str) -> list[dict]:
    await _require_site(site_id)
    items = [json.loads(x) for x in await get_platform_redis().hvals(knowledge_key(site_id))]
    # 新文档在前（文档库的自然顺序），同刻按 id 稳定排序
    return sorted(items, key=lambda d: (d.get("created_at", ""), d["id"]), reverse=True)


async def get_doc(site_id: str, doc_id: str) -> dict | None:
    await _require_site(site_id)
    raw = await get_platform_redis().hget(knowledge_key(site_id), doc_id)
    return json.loads(raw) if raw else None


async def get_blob(site_id: str, doc_id: str) -> bytes | None:
    """取文件原始字节（阅读/下载用）。"""
    await _require_site(site_id)
    raw = await get_platform_redis().get(blob_key(site_id, doc_id))
    return base64.b64decode(raw) if raw else None


async def create_doc(site_id: str, data: dict, content: bytes) -> dict:
    await _require_site(site_id)
    if len(content) > MAX_FILE_BYTES:
        raise FileTooLarge(len(content))
    r = get_platform_redis()
    key = knowledge_key(site_id)
    doc_id = uuid.uuid4().hex[:8]
    name = str(data.get("name") or "").strip()
    await _check_name_unique(r, key, name)
    stored = {
        **{k: v for k, v in data.items() if k != "id"},
        "id": doc_id,
        "size": len(content),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    # 先写内容再写元数据：元数据是「文档存在」的唯一判据，反向顺序会产生无元数据的孤儿 blob
    await r.set(blob_key(site_id, doc_id), base64.b64encode(content).decode("ascii"))
    await r.hset(key, doc_id, json.dumps(stored, ensure_ascii=False))
    await oplog.record(site_id, f"knowledge/{name}", "KNOWLEDGE_CREATED",
                       target=name, params={"doc_id": doc_id, "size": len(content)})
    return stored


async def update_doc(site_id: str, doc_id: str, data: dict) -> dict | None:
    """仅更新元数据（当前仅名称/描述；文件内容创建后不可变）。"""
    await _require_site(site_id)
    r = get_platform_redis()
    key = knowledge_key(site_id)
    raw = await r.hget(key, doc_id)
    if not raw:
        return None
    old = json.loads(raw)
    if "name" in data:
        await _check_name_unique(r, key, str(data.get("name") or "").strip(), exclude_id=doc_id)
    old.update({k: v for k, v in data.items() if k not in ("id", "size", "created_at", "filename", "mime")})
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
    await r.delete(blob_key(site_id, doc_id))  # 内容随元数据一并清除，不留孤儿
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


class FileTooLarge(Exception):
    def __init__(self, size: int):
        super().__init__(f"file exceeds {MAX_FILE_BYTES} bytes (got {size})")
        self.size = size
