import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core import oplog
from backend.app.main import app
from backend.app.modules.knowledge.service import knowledge_key


@pytest.fixture
async def client(fake_platform_redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _make_site(client):
    r = await client.post("/api/sites", json={"id": "sz-test", "name": "深圳测试站"})
    assert r.status_code == 201


async def test_doc_crud_and_name_only_edit(client):
    """CRUD 全流程；PUT 仅提交 name 时 markdown 原值保留（仅名称编辑语义）。"""
    await _make_site(client)

    r = await client.post("/api/knowledge/sz-test", json={
        "name": "运维手册", "description": "首页手册", "markdown": "# 标题\n正文"})
    assert r.status_code == 201
    doc = r.json()
    assert doc["id"]
    assert doc["name"] == "运维手册" and doc["markdown"] == "# 标题\n正文"

    listed = (await client.get("/api/knowledge/sz-test")).json()
    assert [d["id"] for d in listed] == [doc["id"]]

    r = await client.put(f"/api/knowledge/sz-test/{doc['id']}", json={"name": "改名"})
    assert r.status_code == 200
    assert r.json()["name"] == "改名"
    assert r.json()["markdown"] == "# 标题\n正文"

    assert (await client.delete(f"/api/knowledge/sz-test/{doc['id']}")).status_code == 204
    # 删除后不可再命中：列表为空，编辑/删除均 404
    assert (await client.get("/api/knowledge/sz-test")).json() == []
    assert (await client.put(f"/api/knowledge/sz-test/{doc['id']}",
                             json={"name": "x"})).status_code == 404
    assert (await client.delete(f"/api/knowledge/sz-test/{doc['id']}")).status_code == 404


async def test_doc_name_unique(client):
    await _make_site(client)
    r = await client.post("/api/knowledge/sz-test", json={"name": "A", "markdown": "# a"})
    assert r.status_code == 201
    a_id = r.json()["id"]

    # 同站重名创建 → 409
    r = await client.post("/api/knowledge/sz-test", json={"name": "A", "markdown": "# b"})
    assert r.status_code == 409

    # PUT 改名撞他者之名 → 409；保存自身原名放行
    r = await client.post("/api/knowledge/sz-test", json={"name": "B", "markdown": "# b"})
    assert r.status_code == 201
    b_id = r.json()["id"]
    assert (await client.put(f"/api/knowledge/sz-test/{b_id}",
                             json={"name": "A"})).status_code == 409
    assert (await client.put(f"/api/knowledge/sz-test/{b_id}",
                             json={"name": "B"})).status_code == 200

    # 同名约束只在站点内：另一站点可叫 A
    await client.post("/api/sites", json={"id": "sz-other", "name": "另一站"})
    assert (await client.post("/api/knowledge/sz-other",
                              json={"name": "A", "markdown": "# c"})).status_code == 201


async def test_doc_markdown_size_limit_both_paths(client):
    """1M 字符上限：创建与编辑（DocUpdate 的 Annotated metadata 随行）双路径生效。"""
    await _make_site(client)

    r = await client.post("/api/knowledge/sz-test", json={
        "name": "大文档", "markdown": "x" * 1_000_001})
    assert r.status_code == 422

    r = await client.post("/api/knowledge/sz-test", json={
        "name": "边界", "markdown": "x" * 1_000_000})
    assert r.status_code == 201
    doc_id = r.json()["id"]

    # 编辑路径同样受限（metadata 修复断言）
    r = await client.put(f"/api/knowledge/sz-test/{doc_id}",
                         json={"markdown": "x" * 1_000_001})
    assert r.status_code == 422


async def test_doc_blank_markdown_rejected(client):
    """空白 markdown 归一为 None 后被 _need_markdown 拒绝。"""
    await _make_site(client)
    r = await client.post("/api/knowledge/sz-test", json={"name": "空白", "markdown": "   "})
    assert r.status_code == 422
    r = await client.post("/api/knowledge/sz-test", json={"name": "缺失"})
    assert r.status_code == 422


async def test_doc_on_missing_site_404(client):
    r = await client.get("/api/knowledge/no-such")
    assert r.status_code == 404
    r = await client.post("/api/knowledge/no-such", json={"name": "x", "markdown": "# x"})
    assert r.status_code == 404
    r = await client.put("/api/knowledge/no-such/d1", json={"name": "x"})
    assert r.status_code == 404
    r = await client.delete("/api/knowledge/no-such/d1")
    assert r.status_code == 404


async def test_doc_markdown_null_and_blank_not_silently_cleared(client):
    """PUT 提交显式 null/空白 markdown 不静默清正文（编辑与创建同口径，清空走删除重建）。"""
    await _make_site(client)
    r = await client.post("/api/knowledge/sz-test", json={"name": "手册", "markdown": "# 原文"})
    doc_id = r.json()["id"]

    for body in ({"markdown": None}, {"markdown": "   "}):
        r = await client.put(f"/api/knowledge/sz-test/{doc_id}", json=body)
        assert r.status_code == 200
        assert r.json()["markdown"] == "# 原文"

    # 存储层同样未被清掉
    listed = (await client.get("/api/knowledge/sz-test")).json()
    assert listed[0]["markdown"] == "# 原文"


async def test_delete_site_cascades_knowledge_docs(client, fake_platform_redis):
    """删站连带清独立存储的 knowledge 文档 hash（sites/service.py 字面量直写清理）。"""
    await _make_site(client)
    r = await client.post("/api/knowledge/sz-test", json={"name": "手册", "markdown": "# m"})
    assert r.status_code == 201
    assert await fake_platform_redis.exists(knowledge_key("sz-test"))

    assert (await client.delete("/api/sites/sz-test")).status_code == 204
    assert not await fake_platform_redis.exists(knowledge_key("sz-test"))


async def test_doc_oplog_lifecycle(client):
    """建/改/删各记一条：resource=knowledge/<name>，target=名称，id 进 params。"""
    await _make_site(client)
    r = await client.post("/api/knowledge/sz-test", json={"name": "手册", "markdown": "# m"})
    doc_id = r.json()["id"]

    entry = (await oplog.read_recent(1))[0]
    assert entry["operation"] == "KNOWLEDGE_CREATED"
    assert entry["resource"] == "knowledge/手册"
    assert entry["target"] == "手册"
    assert entry["params"]["doc_id"] == doc_id

    await client.put(f"/api/knowledge/sz-test/{doc_id}", json={"name": "手册改"})
    entry = (await oplog.read_recent(1))[0]
    assert entry["operation"] == "KNOWLEDGE_UPDATED"
    assert entry["resource"] == "knowledge/手册改"
    assert entry["params"]["doc_id"] == doc_id

    await client.delete(f"/api/knowledge/sz-test/{doc_id}")
    entry = (await oplog.read_recent(1))[0]
    assert entry["operation"] == "KNOWLEDGE_DELETED"
    assert entry["resource"] == "knowledge/手册改"
    assert entry["params"]["doc_id"] == doc_id
