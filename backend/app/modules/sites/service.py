import json
import uuid
from datetime import datetime, timezone

from backend.app.core import oplog
from backend.app.core.redis import get_platform_redis

SITES_KEY = "ops:sites"  # Set: 全部站点 id（PRD §6.2）
RESOURCE_TYPES = ("servers", "pages", "redis", "mq", "devices")
# 删除站点时一并清理的附属 key：overview 健康 hash、ssh 脚本 hash、knowledge 文档 hash
# （字面量直写，避免跨模块循环导入）
HEALTH_KEY = "ops:health:{site_id}"  # overview/service.py health_key 同格式
SSH_SCRIPTS_KEY = "ops:site:{site_id}:ssh_scripts"  # ssh/service.py _key 同格式
KNOWLEDGE_KEY = "ops:knowledge:{site_id}"  # knowledge/service.py knowledge_key 同格式
LOGS_KEY = "ops:logs:{site_id}"  # logs/service.py 日志源配置同格式
EVENTS_KEY = "ops:events:{site_id}"  # core/events.py 事件时间轴同格式


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
    keys.append(KNOWLEDGE_KEY.format(site_id=site_id))  # 知识库文档随站点删除（独立存储，字面量直写避循环 import）
    keys.append(LOGS_KEY.format(site_id=site_id))  # 日志源配置
    keys.append(EVENTS_KEY.format(site_id=site_id))  # 事件时间轴
    await r.delete(*keys)
    # 知识库文件在磁盘上（ops_data_dir/knowledge/{site_id}/），一并删除
    from backend.app.modules.knowledge.service import delete_site_files
    delete_site_files(site_id)
    # 采样序列随站点删除：该站点的趋势样本再无读者，留着只会成为孤儿 key
    # （写时 TTL 只救活被继续推送的序列，删站后无人推送）。站点段位置随
    # 资源类型不同有三种形态，逐一扫描：
    #   ops:sample:server:{site}:*  /  ops:sample:mq:{site}:*  /  ops:sample:{site}:*
    stale: list[str] = []
    for pat in (f"ops:sample:server:{site_id}:*",
                f"ops:sample:mq:{site_id}:*",
                f"ops:sample:{site_id}:*",
                # 知识库文件内容（每文档一个 key，只能按前缀扫；元数据 hash 已在上面整删）
                f"ops:knowledge:{site_id}:blob:*"):
        stale += [k async for k in r.scan_iter(pat)]
    if stale:
        await r.delete(*stale)
    await r.srem(SITES_KEY, site_id)
    await oplog.record(site_id, "site-config", "SITE_DELETED",
                       target=row.get("name") or site_id, params={"site_id": site_id})
    return True


# ---------- 资源配置（servers / redis / mq / devices，PRD §5.2） ----------
# 决策记录（2026-09-22，用户指令）：内部工具全明文——查询接口返回明文密码，
# 推翻 PRD §5.2 的"密码不回显"要求；更新语义为"提交什么存什么"。


async def migrate_knowledge_back_to_pages() -> None:
    """knowledge→pages 反向迁移（拆分回退，应用启动时执行）：
    仅 knowledge 存在 → RENAME 为 pages；并存 → pages 缺失 id 从 knowledge 并入后删源；
    仅 pages → 不动。幂等。"""
    r = get_platform_redis()
    for sid in await r.smembers(SITES_KEY):
        src = resource_key(sid, "knowledge")
        dst = resource_key(sid, "pages")
        if not await r.exists(src):
            continue
        if not await r.exists(dst):
            await r.rename(src, dst)
            continue
        target_ids = set(await r.hkeys(dst))
        merged = {rid: raw for rid, raw in (await r.hgetall(src)).items() if rid not in target_ids}
        if merged:
            await r.hset(dst, mapping=merged)
        await r.delete(src)


async def _require_site(site_id: str) -> None:
    if not await get_platform_redis().hexists(site_key(site_id), "id"):
        raise NotFound(f"site not found: {site_id}")


async def list_resources(site_id: str, res_type: str, include_password: bool = False) -> list[dict]:
    """列出资源配置。密码默认脱敏（password -> has_password 布尔），接口永不回明文——
    F12/抓包只见掩码；编辑时留空即保持原值，连接测试走后端 get_resource_raw。
    include_password=True 仅供**后端内部**使用（overview 聚合直连），不进任何 API 响应。
    """
    await _require_site(site_id)
    raw = await get_platform_redis().hvals(resource_key(site_id, res_type))
    items = [json.loads(x) for x in raw]
    if not include_password:
        items = [_mask_password(c) for c in items]
    return sorted((_with_kind(res_type, c) for c in items), key=lambda c: c["id"])


def _mask_password(cfg: dict) -> dict:
    c = dict(cfg)
    if "password" in c:
        c["has_password"] = bool(c.pop("password"))
    return c


async def get_resource_raw(site_id: str, res_type: str, resource_id: str) -> dict | None:
    """读原始配置（含密码）。供各资源模块 provider 建连与前端展示共用。"""
    await _require_site(site_id)
    raw = await get_platform_redis().hget(resource_key(site_id, res_type), resource_id)
    return _with_kind(res_type, json.loads(raw)) if raw else None


async def get_resource(site_id: str, res_type: str, resource_id: str) -> dict | None:
    """单查（编辑回填）：同样脱敏，密码留空即保持。"""
    item = await get_resource_raw(site_id, res_type, resource_id)
    return _mask_password(item) if item else item


def _res_label(data: dict, resource_id: str) -> str:
    """oplog 展示用资源名：name 优先，缺省退回 id（内部 id 一律只进 params）。"""
    return str(data.get("name") or resource_id)


def _snap(cfg: dict) -> dict:
    """oplog 配置快照：id 已在 params，不进 diff。"""
    return {k: v for k, v in cfg.items() if k != "id"}


def _with_kind(res_type: str, item: dict) -> dict:
    """pages 资源的派生字段 kind：url > html 两档。

    存储不落 kind（后端/前端都可能写配置），读取时按当前内容派生——
    老数据与手改数据同样得到正确分类，零迁移成本。其他资源类型原样返回。
    """
    if res_type == "pages":
        item["kind"] = "url" if item.get("url") else ("html" if item.get("html") else None)
    return item


async def _check_name_unique(r, key: str, name: str, exclude_id: str | None = None) -> None:
    """同站点同类型下 name 唯一（防快连创建重名）。exclude_id = 编辑时排除自身。"""
    if not name:
        return
    for rid, raw in (await r.hgetall(key)).items():
        if rid == exclude_id:
            continue
        if json.loads(raw).get("name") == name:
            raise DuplicateResource(f"name already in use: {name}")


async def create_resource(site_id: str, res_type: str, data: dict) -> dict:
    await _require_site(site_id)
    r = get_platform_redis()
    key = resource_key(site_id, res_type)
    resource_id = data.get("id") or uuid_hex()
    if await r.hexists(key, resource_id):
        raise DuplicateResource(resource_id)
    name = str(data.get("name") or "").strip()
    await _check_name_unique(r, key, name)  # 同站点同类型 name 唯一
    data = {k: v for k, v in data.items() if k != "kind"}  # kind 是派生字段，不落存储
    stored = {**data, "id": resource_id}
    await r.hset(key, resource_id, json.dumps(stored, ensure_ascii=False))
    label = _res_label(stored, resource_id)
    await oplog.record(site_id, f"{res_type}/{label}", "RESOURCE_CONFIG_CREATED",
                       target=label, params={"resource_id": resource_id},
                       after=_snap(stored))
    return _with_kind(res_type, _mask_password(dict(stored)))


async def update_resource(site_id: str, res_type: str, resource_id: str, data: dict) -> dict | None:
    await _require_site(site_id)
    r = get_platform_redis()
    key = resource_key(site_id, res_type)
    raw = await r.hget(key, resource_id)
    if not raw:
        return None
    old = json.loads(raw)
    # 改名时同样校验唯一（排除自身）
    if "name" in data:
        await _check_name_unique(r, key, str(data.get("name") or "").strip(), exclude_id=resource_id)
    # 提交什么存什么（exclude_unset 只带显式提交的字段）；明文策略下编辑即覆盖
    new = {**old, **{k: v for k, v in data.items() if k != "kind"}, "id": resource_id}
    before, after = oplog.diff(old, new)  # 只记变化键，避免 oplog 膨胀
    await r.hset(key, resource_id, json.dumps(new, ensure_ascii=False))
    name = _res_label(new, resource_id)
    await oplog.record(site_id, f"{res_type}/{name}", "RESOURCE_CONFIG_UPDATED",
                       target=name, params={"resource_id": resource_id},
                       before=before, after=after)
    return _with_kind(res_type, _mask_password(dict(new)))


async def delete_resource(site_id: str, res_type: str, resource_id: str) -> bool:
    await _require_site(site_id)
    r = get_platform_redis()
    key = resource_key(site_id, res_type)
    raw = await r.hget(key, resource_id)
    if not raw:
        return False
    cfg = json.loads(raw)
    name = _res_label(cfg, resource_id)
    await r.hdel(key, resource_id)
    await oplog.record(site_id, f"{res_type}/{name}", "RESOURCE_CONFIG_DELETED",
                       target=name, params={"resource_id": resource_id},
                       before=_snap(cfg))
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
                item.pop("kind", None)  # kind 是读取时派生的，不落存储
                await r.hset(resource_key(sid, t), item["id"], json.dumps(item, ensure_ascii=False))

    await oplog.record("-", "site-config", "IMPORT_CONFIG", params={"sites": len(sites)})
    return len(sites)
