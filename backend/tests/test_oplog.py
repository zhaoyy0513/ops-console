import json

from backend.app.core import oplog
from backend.app.core.oplog import OPLOG_KEY, OPLOG_MAX
from backend.app.modules.knowledge import service as knowledge_service
from backend.app.modules.sites import service as sites_service


async def test_oplog_trimmed_to_cap(fake_platform_redis):
    """写入超过上限后仅保留最近 OPLOG_MAX 条（当前 320）。"""
    for i in range(OPLOG_MAX + 5):
        await oplog.record(site="s", resource="redis-01", operation="DELETE_KEY", target=f"k{i}")

    r = fake_platform_redis
    assert await r.llen(OPLOG_KEY) == OPLOG_MAX
    newest = await r.lindex(OPLOG_KEY, 0)
    assert f"k{OPLOG_MAX + 4}" in newest  # 最新在前


async def test_read_recent_returns_latest_n(fake_platform_redis):
    for i in range(30):
        await oplog.record(site="s", resource="redis-01", operation="SET_KEY", target=f"k{i}")

    entries = await oplog.read_recent(20)
    assert len(entries) == 20
    assert entries[0]["target"] == "k29"  # 最新
    assert entries[19]["target"] == "k10"  # 最早仍在保留窗内


async def test_read_page(fake_platform_redis):
    for i in range(25):
        await oplog.record(site="s", resource="redis-01", operation="SET_KEY", target=f"k{i}")

    items, total = await oplog.read_page(page=2, size=20)
    assert total == 25
    assert len(items) == 5  # 末页余量


# ---------- P0-7：配置变更 diff ----------


async def _seed_redis(fake_platform_redis):
    await sites_service.create_site({"id": "s1", "name": "site"})
    await sites_service.create_resource(
        "s1", "redis", {"id": "r1", "name": "r1", "host": "h1", "port": 6379, "password": "old-secret"}
    )


async def test_update_records_only_changed_keys(fake_platform_redis):
    await _seed_redis(fake_platform_redis)
    await sites_service.update_resource("s1", "redis", "r1", {"name": "r1", "host": "h2", "port": 6379})

    entry = (await oplog.read_recent(1))[0]
    assert entry["operation"] == "RESOURCE_CONFIG_UPDATED"
    assert entry["before"] == {"host": "h1"}  # 未变的 name/port 不出现
    assert entry["after"] == {"host": "h2"}


async def test_password_masked_in_diff(fake_platform_redis):
    await _seed_redis(fake_platform_redis)
    await sites_service.update_resource("s1", "redis", "r1", {"password": "new-secret"})

    entry = (await oplog.read_recent(1))[0]
    assert entry["before"] == {"password": "***"}
    assert entry["after"] == {"password": "***"}
    # 明文一个字节都不能落进 oplog（含 create 那条）
    raw = "".join(await fake_platform_redis.lrange(OPLOG_KEY, 0, -1))
    assert "old-secret" not in raw and "new-secret" not in raw


async def test_create_has_only_after_and_delete_only_before(fake_platform_redis):
    await _seed_redis(fake_platform_redis)

    created = (await oplog.read_recent(1))[0]
    assert created["operation"] == "RESOURCE_CONFIG_CREATED"
    assert created["before"] is None
    assert created["after"]["host"] == "h1" and created["after"]["password"] == "***"
    assert "id" not in created["after"]  # 内部 id 只进 params

    await sites_service.delete_resource("s1", "redis", "r1")
    deleted = (await oplog.read_recent(1))[0]
    assert deleted["operation"] == "RESOURCE_CONFIG_DELETED"
    assert deleted["after"] is None
    assert deleted["before"]["host"] == "h1" and deleted["before"]["password"] == "***"


async def _chunks(data: bytes, size: int = 1024):
    """create_doc 收字节块迭代器（流式写盘）。"""
    for i in range(0, len(data), size):
        yield data[i:i + size]


async def test_knowledge_records_metadata_only(fake_platform_redis):
    await sites_service.create_site({"id": "s1", "name": "site"})
    content = b"%PDF-1.4 secret body"
    await knowledge_service.create_doc(
        "s1", {"name": "手册", "description": "d", "filename": "a.pdf", "mime": "application/pdf"},
        _chunks(content),
    )
    created = (await oplog.read_recent(1))[0]
    assert created["after"] == {
        "name": "手册", "description": "d", "filename": "a.pdf", "mime": "application/pdf", "size": len(content),
    }
    assert "secret body" not in json.dumps(created, ensure_ascii=False)  # 内容本身不记录

    doc_id = (await fake_platform_redis.hkeys(knowledge_service.knowledge_key("s1")))[0]
    await knowledge_service.update_doc("s1", doc_id, {"description": "d2"})
    updated = (await oplog.read_recent(1))[0]
    assert updated["before"] == {"description": "d"}
    assert updated["after"] == {"description": "d2"}


async def test_legacy_record_without_diff_is_readable(fake_platform_redis):
    """老记录（无 before/after 字段）照常读出，不抛异常。"""
    legacy = {"time": "2026-09-01T00:00:00+00:00", "site": "s", "resource": "redis-01",
              "operation": "SET_KEY", "target": "k", "params": None, "result": "SUCCESS",
              "error": None, "caller": "-", "caller_ip": "-"}
    await fake_platform_redis.lpush(OPLOG_KEY, json.dumps(legacy, ensure_ascii=False))

    items, total = await oplog.read_page()
    assert total == 1 and items[0]["target"] == "k"
    assert "before" not in items[0] and "after" not in items[0]
    assert (await oplog.read_recent(1))[0]["operation"] == "SET_KEY"
