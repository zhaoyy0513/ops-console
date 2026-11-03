"""知识库服务层（文件系统存储版）。

元数据：Redis hash `ops:knowledge:{site_id}`（field=doc_id，value=JSON）。
文件内容：磁盘 `{OPS_DATA_DIR}/knowledge/{site_id}/{doc_id}{ext}`——200MB 级文件
不适合整份塞进 Redis（内存与主从同步压力），文件系统 + 流式写入才扛得住。

历史兼容：最早版本把 markdown 存在元数据里（无独立文件）。这类旧文档在
读内容时按 text/markdown 即时合成，删除时同样清掉 Redis blob 遗留。
"""

import base64
import json
import re
import shutil
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

from backend.app.core import oplog
from backend.app.core.config import settings
from backend.app.core.redis import get_platform_redis
from backend.app.modules.sites.service import site_key

# 单文件上限 200MB（原始字节；流式写入磁盘，不占后端内存）
MAX_FILE_BYTES = 200 * 1024 * 1024
# 流式拷贝块大小（1MB）
COPY_CHUNK = 1024 * 1024

# 文件名里的非法字符（Windows 保留字符 + 路径分隔符），统一替换为下划线
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def knowledge_key(site_id: str) -> str:
    """元数据 Hash：field=doc_id，value=JSON（不含文件内容与存储路径）。"""
    return f"ops:knowledge:{site_id}"


def blob_key(site_id: str, doc_id: str) -> str:
    """旧版 Redis blob key（兼容读取历史文档，新文档不再写这里）。"""
    return f"ops:knowledge:{site_id}:blob:{doc_id}"


def _storage_root() -> Path:
    return Path(settings.ops_data_dir) / "knowledge"


def _file_path(site_id: str, doc_id: str, filename: str) -> Path:
    """磁盘路径：{root}/{site_id}/{doc_id}{ext}。扩展名保留给预览器/下载用，
    正文用 doc_id 避免文件名中的中文/空格/特殊字符在文件系统上的兼容问题。"""
    ext = Path(filename).suffix[:16]
    return _storage_root() / site_id / f"{doc_id}{ext}"


async def _require_site(site_id: str) -> None:
    if not await get_platform_redis().hexists(site_key(site_id), "id"):
        raise NotFound(f"site not found: {site_id}")


def _snap(doc: dict) -> dict:
    """oplog 快照：只记元数据（id/created_at 不进 diff，文件内容从不记录）。"""
    return {k: v for k, v in doc.items() if k not in ("id", "created_at")}


async def list_docs(site_id: str) -> list[dict]:
    await _require_site(site_id)
    items = [json.loads(x) for x in await get_platform_redis().hvals(knowledge_key(site_id))]
    # 新文档在前（文档库的自然顺序），同刻按 id 稳定排序
    return sorted(items, key=lambda d: (d.get("created_at", ""), d["id"]), reverse=True)


async def get_doc(site_id: str, doc_id: str) -> dict | None:
    await _require_site(site_id)
    raw = await get_platform_redis().hget(knowledge_key(site_id), doc_id)
    return json.loads(raw) if raw else None


async def get_file(site_id: str, doc_id: str) -> tuple[bytes, str] | None:
    """返回 (文件字节, 文件名)。兼容两类历史文档：
    ① 旧版 Redis blob（base64）② 旧版 markdown 字段（合成 text/markdown）。
    新文档在磁盘上，走 storage_file() 直接流式返回，不经此函数。"""
    doc = await get_doc(site_id, doc_id)
    if doc is None:
        return None
    r = get_platform_redis()

    legacy_blob = await r.get(blob_key(site_id, doc_id))
    if legacy_blob:
        return base64.b64decode(legacy_blob), doc.get("filename") or "doc.md"
    if doc.get("markdown"):
        return doc["markdown"].encode("utf-8"), (doc.get("filename") or "doc.md")
    return None


def storage_file(site_id: str, doc_id: str, filename: str) -> Path | None:
    """磁盘文件路径（存在才返回 Path）。新文档走这里流式返回。"""
    f = _file_path(site_id, doc_id, filename)
    return f if f.is_file() else None


async def _unique_name(r, key: str, name: str, exclude_id: str | None = None) -> str:
    """名称去重：重名时自动追加 -2 / -3 …（上传体验优先于报错）。
    exclude_id = 编辑时排除自身。"""
    if not name:
        return name
    taken = {
        json.loads(raw).get("name")
        for sid, raw in (await r.hgetall(key)).items()
        if sid != exclude_id
    }
    if name not in taken:
        return name
    n = 2
    while f"{name}-{n}" in taken:
        n += 1
    return f"{name}-{n}"


async def create_doc(site_id: str, data: dict, chunks: AsyncIterator[bytes]) -> dict:
    """流式写盘：chunks 是字节块异步迭代器（1MB/块，内存恒定）。

    直接写正式路径，不落临时文件：元数据是「文档存在」的唯一判据，写坏的半份文件
    没有元数据不会被读到（get_content 先查 Redis 再碰文件）；失败/超限时删掉残file。
    先写盘成功再写元数据——反向会在元数据写失败时留孤儿文件。"""
    await _require_site(site_id)
    r = get_platform_redis()
    key = knowledge_key(site_id)
    doc_id = uuid.uuid4().hex[:8]
    name = await _unique_name(r, key, str(data.get("name") or "").strip())
    filename = data.get("filename") or "file"

    dest = _file_path(site_id, doc_id, filename)
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with dest.open("wb") as fh:
            async for chunk in chunks:
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise FileTooLarge(size)
                fh.write(chunk)
    except BaseException:
        dest.unlink(missing_ok=True)  # 超限/磁盘满/中断，不留残file
        raise

    stored = {
        **{k: v for k, v in data.items() if k != "id"},
        "name": name,
        "id": doc_id,
        "size": size,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    await r.hset(key, doc_id, json.dumps(stored, ensure_ascii=False))
    await oplog.record(site_id, f"knowledge/{name}", "KNOWLEDGE_CREATED",
                       target=name, params={"doc_id": doc_id, "size": size},
                       after=_snap(stored))
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
    new = {**old, **{k: v for k, v in data.items() if k not in ("id", "size", "created_at", "filename", "mime")},
           "id": doc_id}
    if new["name"] != old.get("name"):
        new["name"] = await _unique_name(r, key, new["name"], exclude_id=doc_id)
    before, after = oplog.diff(old, new)  # 只记变化键（仅元数据，内容不可变）
    await r.hset(key, doc_id, json.dumps(new, ensure_ascii=False))
    await oplog.record(site_id, f"knowledge/{new['name']}", "KNOWLEDGE_UPDATED",
                       target=new["name"], params={"doc_id": doc_id},
                       before=before, after=after)
    return new


async def delete_doc(site_id: str, doc_id: str) -> bool:
    await _require_site(site_id)
    r = get_platform_redis()
    key = knowledge_key(site_id)
    raw = await r.hget(key, doc_id)
    if not raw:
        return False
    doc = json.loads(raw)
    name = str(doc.get("name") or doc_id)
    await r.hdel(key, doc_id)
    await r.delete(blob_key(site_id, doc_id))  # 兼容期：旧版 blob 一并清除
    f = _file_path(site_id, doc_id, doc.get("filename") or "")
    f.unlink(missing_ok=True)  # 磁盘文件随元数据一并删除
    await oplog.record(site_id, f"knowledge/{name}", "KNOWLEDGE_DELETED",
                       target=name, params={"doc_id": doc_id})
    return True


def delete_site_files(site_id: str) -> None:
    """删站时连带删除该站点整个文件目录（由 sites/service 在删站流程调用）。"""
    root = _storage_root() / site_id
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


async def _check_name_unique(r, key: str, name: str, exclude_id: str | None = None) -> None:
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
