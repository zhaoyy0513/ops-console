import json

from backend.app.modules.sites import service


async def test_reverse_migrate_renames_knowledge_key(fake_platform_redis):
    """仅 knowledge 存在且 pages 不存在 → 原子 RENAME 回 pages。"""
    r = fake_platform_redis
    await r.sadd(service.SITES_KEY, "sz-legacy")
    await r.hset(service.resource_key("sz-legacy", "knowledge"), "p1",
                 json.dumps({"id": "p1", "name": "测试卡", "url": "https://a.b"}))
    await service.migrate_knowledge_back_to_pages()
    assert json.loads(await r.hget(service.resource_key("sz-legacy", "pages"), "p1"))["name"] == "测试卡"
    assert not await r.exists(service.resource_key("sz-legacy", "knowledge"))


async def test_reverse_migrate_merges_when_both_exist(fake_platform_redis):
    """并存：knowledge 中 pages 缺失的 id 并入，pages 已有 id 以 pages 为准，源删除。"""
    r = fake_platform_redis
    await r.sadd(service.SITES_KEY, "sz-both")
    await r.hset(service.resource_key("sz-both", "knowledge"), mapping={
        "p1": json.dumps({"id": "p1", "name": "迁移来的", "html": "<p>x</p>"}),
        "p2": json.dumps({"id": "p2", "name": "两边同id-旧", "url": "https://old"}),
    })
    await r.hset(service.resource_key("sz-both", "pages"), "p2",
                 json.dumps({"id": "p2", "name": "两边同id-新", "url": "https://new"}))
    await service.migrate_knowledge_back_to_pages()
    dst = service.resource_key("sz-both", "pages")
    assert json.loads(await r.hget(dst, "p1"))["name"] == "迁移来的"
    assert json.loads(await r.hget(dst, "p2"))["name"] == "两边同id-新"
    assert not await r.exists(service.resource_key("sz-both", "knowledge"))


async def test_reverse_migrate_noop_when_only_pages(fake_platform_redis):
    r = fake_platform_redis
    await r.sadd(service.SITES_KEY, "sz-new")
    await r.hset(service.resource_key("sz-new", "pages"), "p1",
                 json.dumps({"id": "p1", "name": "原页", "url": "https://a.b"}))
    await service.migrate_knowledge_back_to_pages()
    assert await r.hget(service.resource_key("sz-new", "pages"), "p1")
