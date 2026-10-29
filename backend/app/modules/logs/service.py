"""日志查看器服务层：日志源 CRUD（独立存储）+ 读取编排。

存储：ops:logs:{site_id} Hash，field=source_id，value=JSON {id, label, path}。
读取的 SSH 目标：站点下按 id 排序的第一个 Server 资源（日志源只存路径，
不绑定 server；站点多 Server 时取第一个，后续如需可选 server 再加字段）。
"""

import json
import uuid
from typing import Any

from backend.app.core import oplog
from backend.app.core.redis import get_platform_redis
from backend.app.modules.sites import service as sites_service
from backend.app.modules.sites.service import NotFound, site_key
from backend.app.shared.concurrency import get_semaphore
from backend.app.shared.retry import with_retry

from .provider import DEFAULT_LINES, SSHLogsProvider, clamp_lines

MAX_LABEL = 200
MAX_PATH = 4096


def logs_key(site_id: str) -> str:
    return f"ops:logs:{site_id}"


async def _require_site(site_id: str) -> None:
    if not await get_platform_redis().hexists(site_key(site_id), "id"):
        raise NotFound(f"site not found: {site_id}")


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    """只接受 label/path；label 去空白非空，path 必须绝对路径且无 NUL。"""
    out: dict[str, Any] = {}
    if "label" in data:
        label = str(data["label"] or "").strip()
        if not label:
            raise ValueError("label is required")
        if len(label) > MAX_LABEL:
            raise ValueError(f"label too long (max {MAX_LABEL})")
        out["label"] = label
    if "path" in data:
        path = str(data["path"] or "").strip()
        if not path.startswith("/"):
            raise ValueError("path must be absolute")
        if "\x00" in path:
            raise ValueError("path contains NUL")
        if len(path) > MAX_PATH:
            raise ValueError(f"path too long (max {MAX_PATH})")
        out["path"] = path
    return out


async def list_sources(site_id: str) -> list[dict[str, Any]]:
    await _require_site(site_id)
    items = [json.loads(x) for x in await get_platform_redis().hvals(logs_key(site_id))]
    return sorted(items, key=lambda s: (s.get("label", ""), s["id"]))


async def get_source(site_id: str, source_id: str) -> dict[str, Any] | None:
    await _require_site(site_id)
    raw = await get_platform_redis().hget(logs_key(site_id), source_id)
    return json.loads(raw) if raw else None


async def _check_label_unique(r, key: str, label: str, exclude_id: str | None = None) -> None:
    for sid, raw in (await r.hgetall(key)).items():
        if sid != exclude_id and json.loads(raw).get("label") == label:
            raise DuplicateLabel(f"label already in use: {label}")


async def create_source(site_id: str, data: dict[str, Any]) -> dict[str, Any]:
    await _require_site(site_id)
    clean = _clean(data)
    if "label" not in clean or "path" not in clean:
        raise ValueError("label and path are required")
    r = get_platform_redis()
    key = logs_key(site_id)
    await _check_label_unique(r, key, clean["label"])
    source_id = uuid.uuid4().hex[:8]
    stored = {**clean, "id": source_id}
    await r.hset(key, source_id, json.dumps(stored, ensure_ascii=False))
    await oplog.record(site_id, f"logs/{stored['label']}", "LOGS_SOURCE_CREATED",
                       target=stored["label"], params={"source_id": source_id},
                       after={"label": stored["label"], "path": stored["path"]})
    return stored


async def update_source(site_id: str, source_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    await _require_site(site_id)
    r = get_platform_redis()
    key = logs_key(site_id)
    raw = await r.hget(key, source_id)
    if not raw:
        return None
    old = json.loads(raw)
    clean = _clean(data)
    if "label" in clean:
        await _check_label_unique(r, key, clean["label"], exclude_id=source_id)
    new = {**old, **clean, "id": source_id}
    before, after = oplog.diff(old, new)
    await r.hset(key, source_id, json.dumps(new, ensure_ascii=False))
    await oplog.record(site_id, f"logs/{new['label']}", "LOGS_SOURCE_UPDATED",
                       target=new["label"], params={"source_id": source_id},
                       before=before, after=after)
    return new


async def delete_source(site_id: str, source_id: str) -> bool:
    await _require_site(site_id)
    r = get_platform_redis()
    key = logs_key(site_id)
    raw = await r.hget(key, source_id)
    if not raw:
        return False
    source = json.loads(raw)
    await r.hdel(key, source_id)
    await oplog.record(site_id, f"logs/{source['label']}", "LOGS_SOURCE_DELETED",
                       target=source["label"], params={"source_id": source_id},
                       before={"label": source["label"], "path": source["path"]})
    return True


def _in_band_error(code: str, message: str) -> dict[str, Any]:
    """读取失败但页面应保留已加载内容：200 + error_code，而不是 5xx。"""
    return {
        "content": "",
        "start_offset": 0,
        "next_offset": 0,
        "size": 0,
        "inode": "",
        "eof": False,
        "truncated": False,
        "error_code": code,
        "error": message,
    }


def safe_join(dir_path: str, name: str) -> str:
    """目录 + 文件名拼成绝对路径。文件名只允许单段（不含分隔符/上跳），
    防止通过 file 参数逃出白名单目录。"""
    if not name or name in (".", "..") or "/" in name or "\\" in name or "\x00" in name:
        raise ValueError("invalid file name")
    return dir_path.rstrip("/") + "/" + name


async def _first_server(site_id: str) -> dict[str, Any] | None:
    servers = await sites_service.list_resources(site_id, "servers", include_password=True)
    return servers[0] if servers else None  # list_resources 已按 id 排序


async def list_files(site_id: str, source_id: str) -> dict[str, Any]:
    """列出日志源目录下的文件（只 stat 不读内容，与文件大小无关）。"""
    source = await get_source(site_id, source_id)
    if source is None:
        raise NotFound(f"log source not found: {source_id}")
    server = await _first_server(site_id)
    if server is None:
        return {"files": [], "truncated": False, "error_code": "NO_SERVER",
                "error": "no server configured for this site"}

    provider = SSHLogsProvider(server)
    async with get_semaphore("ssh"):
        return await with_retry(lambda: provider.list_files(source["path"]))()


async def read_source(site_id: str, source_id: str, *, file: str = "",
                      mode: str = "tail", offset: int = 0,
                      kw: str = "", lines: int = DEFAULT_LINES) -> dict[str, Any]:
    source = await get_source(site_id, source_id)
    if source is None:
        raise NotFound(f"log source not found: {source_id}")
    if mode == "search" and not kw.strip():
        raise ValueError("search keyword is required")

    # 传了 file 就走「目录 + 单段文件名」；不传则按旧语义把 path 当文件读（兼容）
    target = safe_join(source["path"], file) if file else source["path"]

    server = await _first_server(site_id)
    if server is None:
        return _in_band_error("NO_SERVER", "no server configured for this site")

    provider = SSHLogsProvider(server)
    call = with_retry(lambda: provider.read(
        target, mode=mode, offset=max(0, int(offset)), kw=kw,
        lines=clamp_lines(lines),
    ))
    async with get_semaphore("ssh"):
        return await call()


class DuplicateLabel(Exception):
    pass
