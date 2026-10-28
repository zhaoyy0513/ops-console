import json

from backend.app.modules.sites import service


async def test_migrate_renames_pages_key(fake_platform_redis):
    """旧 key 存在且目标不存在 → 原子 RENAME。"""
    r = fake_platform_redis
    await r.sadd(service.SITES_KEY, "sz-legacy")
    await r.hset(service.resource_key("sz-legacy", "pages"), "p1",
                 json.dumps({"id": "p1", "name": "旧页", "url": "https://a.b"}))
    await service.migrate_legacy_pages()
    assert json.loads(await r.hget(service.resource_key("sz-legacy", "knowledge"), "p1"))["name"] == "旧页"
    assert not await r.exists(service.resource_key("sz-legacy", "pages"))


async def test_migrate_merges_when_both_exist(fake_platform_redis):
    """降级窗口两边都有数据：源中目标缺失的 id 并入，目标已有 id 以目标为准，源删除。"""
    r = fake_platform_redis
    await r.sadd(service.SITES_KEY, "sz-both")
    await r.hset(service.resource_key("sz-both", "pages"), mapping={
        "p1": json.dumps({"id": "p1", "name": "降级期新建", "url": "https://x.y"}),
        "p2": json.dumps({"id": "p2", "name": "旧版同 id", "url": "https://old"}),
    })
    await r.hset(service.resource_key("sz-both", "knowledge"), "p2",
                 json.dumps({"id": "p2", "name": "新版同 id", "markdown": "# new"}))
    await service.migrate_legacy_pages()
    dst = service.resource_key("sz-both", "knowledge")
    assert json.loads(await r.hget(dst, "p1"))["name"] == "降级期新建"  # 源并入
    assert json.loads(await r.hget(dst, "p2"))["name"] == "新版同 id"  # 目标为准
    assert not await r.exists(service.resource_key("sz-both", "pages"))


async def test_migrate_noop_when_only_target(fake_platform_redis):
    r = fake_platform_redis
    await r.sadd(service.SITES_KEY, "sz-new")
    await r.hset(service.resource_key("sz-new", "knowledge"), "k1",
                 json.dumps({"id": "k1", "name": "新", "url": "https://a.b"}))
    await service.migrate_legacy_pages()  # 不抛错、数据不动
    assert await r.hget(service.resource_key("sz-new", "knowledge"), "k1")


async def test_import_accepts_legacy_pages_field(fake_platform_redis):
    """旧版导出文件里的 pages 数组导入后落到 knowledge。"""
    await service.import_all([{
        "id": "sz-old", "name": "旧站",
        "pages": [{"id": "p1", "name": "旧导出", "url": "https://a.b"}],
    }])
    raw = await fake_platform_redis.hget(service.resource_key("sz-old", "knowledge"), "p1")
    assert json.loads(raw)["name"] == "旧导出"
