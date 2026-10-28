import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core import oplog
from backend.app.main import app
from backend.app.modules.knowledge.service import blob_key, knowledge_key


@pytest.fixture
async def client(fake_platform_redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _make_site(client):
    r = await client.post("/api/sites", json={"id": "sz-test", "name": "深圳测试站"})
    assert r.status_code == 201


def _upload(name: str = "手册", content: bytes = b"# hello", filename: str = "doc.md",
            mime: str = "text/markdown"):
    return {"file": (filename, content, mime)}, {"name": name, "description": ""}


async def test_doc_upload_list_read_delete(client):
    """上传任意文件 → 列表只见元数据 → 内容端点回原始字节 → 删除后 404。"""
    await _make_site(client)
    files, form = _upload(content="# 标题\n正文".encode(), filename="手册.md")

    r = await client.post("/api/knowledge/sz-test", files=files, data=form)
    assert r.status_code == 201
    doc = r.json()
    assert doc["name"] == "手册"
    assert doc["filename"] == "手册.md"
    assert doc["mime"] == "text/markdown"
    assert doc["size"] == len("# 标题\n正文".encode())
    assert "content" not in doc and "markdown" not in doc  # 元数据不含内容

    listed = (await client.get("/api/knowledge/sz-test")).json()
    assert [d["id"] for d in listed] == [doc["id"]]

    # 内容端点：原始字节 + 原 MIME
    r = await client.get(f"/api/knowledge/sz-test/{doc['id']}/content")
    assert r.status_code == 200
    assert r.content == "# 标题\n正文".encode()
    assert r.headers["content-type"].startswith("text/markdown")
    assert "filename*=UTF-8''" in r.headers["content-disposition"]

    assert (await client.delete(f"/api/knowledge/sz-test/{doc['id']}")).status_code == 204
    assert (await client.get("/api/knowledge/sz-test")).json() == []
    assert (await client.get(f"/api/knowledge/sz-test/{doc['id']}/content")).status_code == 404


async def test_doc_name_defaults_to_filename(client):
    """name 留空取文件名去扩展名。"""
    await _make_site(client)
    files, _ = _upload(name="", content=b"x", filename="部署清单.pdf", mime="application/pdf")
    r = await client.post("/api/knowledge/sz-test", files=files, data={"name": "", "description": ""})
    assert r.status_code == 201
    assert r.json()["name"] == "部署清单"


async def test_doc_binary_content_roundtrip(client):
    """二进制文件（非 UTF-8）原样存取——落库 base64、读回还原为原始字节。"""
    await _make_site(client)
    payload = bytes(range(256)) * 4
    files, form = _upload(name="bin", content=payload, filename="a.bin",
                          mime="application/octet-stream")
    r = await client.post("/api/knowledge/sz-test", files=files, data=form)
    assert r.status_code == 201
    doc_id = r.json()["id"]
    r = await client.get(f"/api/knowledge/sz-test/{doc_id}/content")
    assert r.content == payload


async def test_doc_size_limit(client):
    """1MB 上限：1_000_001 字节 413，1_000_000 字节放行。"""
    await _make_site(client)
    files, form = _upload(name="超限", content=b"x" * 1_000_001, filename="big.bin")
    r = await client.post("/api/knowledge/sz-test", files=files, data=form)
    assert r.status_code == 413

    files, form = _upload(name="边界", content=b"x" * 1_000_000, filename="edge.bin")
    r = await client.post("/api/knowledge/sz-test", files=files, data=form)
    assert r.status_code == 201
    assert r.json()["size"] == 1_000_000


async def test_doc_name_unique(client):
    await _make_site(client)
    files, form = _upload(name="A")
    a_id = (await client.post("/api/knowledge/sz-test", files=files, data=form)).json()["id"]

    files, form = _upload(name="A")
    assert (await client.post("/api/knowledge/sz-test", files=files, data=form)).status_code == 409

    files, form = _upload(name="B")
    b_id = (await client.post("/api/knowledge/sz-test", files=files, data=form)).json()["id"]
    assert (await client.put(f"/api/knowledge/sz-test/{b_id}", json={"name": "A"})).status_code == 409
    assert (await client.put(f"/api/knowledge/sz-test/{b_id}", json={"name": "B"})).status_code == 200

    # 同名约束只在站点内
    await client.post("/api/sites", json={"id": "sz-other", "name": "另一站"})
    files, form = _upload(name="A")
    assert (await client.post("/api/knowledge/sz-other", files=files, data=form)).status_code == 201
    assert a_id


async def test_doc_rename_keeps_file_and_ignores_content_fields(client):
    """PUT 仅改名：文件字节不变；提交 filename/mime/size 等字段被忽略（不可篡改元数据）。"""
    await _make_site(client)
    files, form = _upload(name="原名", content=b"payload", filename="a.txt", mime="text/plain")
    doc_id = (await client.post("/api/knowledge/sz-test", files=files, data=form)).json()["id"]

    r = await client.put(f"/api/knowledge/sz-test/{doc_id}", json={
        "name": "新名", "filename": "hacked.exe", "mime": "application/x-msdownload", "size": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "新名"
    assert body["filename"] == "a.txt" and body["mime"] == "text/plain" and body["size"] == 7

    r = await client.get(f"/api/knowledge/sz-test/{doc_id}/content")
    assert r.content == b"payload"


async def test_doc_on_missing_site_404(client):
    files, form = _upload(name="x")
    assert (await client.get("/api/knowledge/no-such")).status_code == 404
    assert (await client.post("/api/knowledge/no-such", files=files, data=form)).status_code == 404
    assert (await client.put("/api/knowledge/no-such/d1", json={"name": "x"})).status_code == 404
    assert (await client.delete("/api/knowledge/no-such/d1")).status_code == 404


async def test_delete_site_cascades_metadata_and_blobs(client, fake_platform_redis):
    """删站连带清元数据 hash 与所有内容 key。"""
    await _make_site(client)
    files, form = _upload(name="手册")
    doc_id = (await client.post("/api/knowledge/sz-test", files=files, data=form)).json()["id"]
    assert await fake_platform_redis.exists(knowledge_key("sz-test"))
    assert await fake_platform_redis.exists(blob_key("sz-test", doc_id))

    assert (await client.delete("/api/sites/sz-test")).status_code == 204
    assert not await fake_platform_redis.exists(knowledge_key("sz-test"))
    assert not await fake_platform_redis.exists(blob_key("sz-test", doc_id))


async def test_doc_delete_removes_blob(client, fake_platform_redis):
    """删文档同时删内容 key（不留孤儿 blob）。"""
    await _make_site(client)
    files, form = _upload(name="手册")
    doc_id = (await client.post("/api/knowledge/sz-test", files=files, data=form)).json()["id"]
    assert (await client.delete(f"/api/knowledge/sz-test/{doc_id}")).status_code == 204
    assert not await fake_platform_redis.exists(blob_key("sz-test", doc_id))


async def test_doc_oplog_lifecycle(client):
    """建/改/删各记一条：resource=knowledge/<name>，target=名称，id 进 params。"""
    await _make_site(client)
    files, form = _upload(name="手册")
    doc_id = (await client.post("/api/knowledge/sz-test", files=files, data=form)).json()["id"]

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
