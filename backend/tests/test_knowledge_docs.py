import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core import oplog
from backend.app.core.config import settings
from backend.app.main import app
from backend.app.modules.knowledge.service import knowledge_key


@pytest.fixture
async def client(fake_platform_redis, tmp_path, monkeypatch):
    # 文件落盘指到临时目录：不污染用户主目录，测试结束自动清理
    object.__setattr__(settings, "ops_data_dir", str(tmp_path))  # Settings 是 frozen dataclass
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _make_site(client):
    r = await client.post("/api/sites", json={"id": "sz-test", "name": "深圳测试站"})
    assert r.status_code == 201


def _upload(name: str = "手册", content: bytes = b"# hello", filename: str = "doc.md",
            mime: str = "text/markdown"):
    return {"file": (filename, content, mime)}, {"name": name, "description": ""}


async def test_doc_upload_list_read_delete(client):
    """上传 → 列表只见元数据 → content 回原始字节（inline 头已移除防 IDM）→ 删除。"""
    await _make_site(client)
    payload = "# 标题\n正文".encode()
    files, form = _upload(content=payload, filename="手册.md")

    r = await client.post("/api/knowledge/sz-test", files=files, data=form)
    assert r.status_code == 201
    doc = r.json()
    assert doc["name"] == "手册"
    assert doc["filename"] == "手册.md"
    assert doc["mime"] == "text/markdown"
    assert doc["size"] == len(payload)
    assert "markdown" not in doc  # 内容不在元数据里

    listed = (await client.get("/api/knowledge/sz-test")).json()
    assert [d["id"] for d in listed] == [doc["id"]]

    # content：原始字节 + MIME；不带 Content-Disposition（防 IDM 拦截）
    r = await client.get(f"/api/knowledge/sz-test/{doc['id']}/content")
    assert r.status_code == 200
    assert r.content == payload
    assert r.headers["content-type"].startswith("text/markdown")
    assert "content-disposition" not in r.headers

    assert (await client.delete(f"/api/knowledge/sz-test/{doc['id']}")).status_code == 204
    assert (await client.get("/api/knowledge/sz-test")).json() == []
    assert (await client.get(f"/api/knowledge/sz-test/{doc['id']}/content")).status_code == 404


async def test_doc_name_defaults_to_filename_without_ext(client):
    """名称自动取文件名去扩展名。"""
    await _make_site(client)
    files, _ = _upload(name="", content=b"x", filename="部署清单.pdf", mime="application/pdf")
    r = await client.post("/api/knowledge/sz-test", files=files, data={"name": "", "description": ""})
    assert r.status_code == 201
    assert r.json()["name"] == "部署清单"


async def test_doc_name_auto_dedup_suffix(client):
    """上传重名自动追加 -2 / -3（不报 409，上传体验优先）。"""
    await _make_site(client)

    async def up(name):
        files, form = _upload(name=name, content=b"x")
        return (await client.post("/api/knowledge/sz-test", files=files, data=form)).json()["name"]

    assert await up("报告") == "报告"
    assert await up("报告") == "报告-2"
    assert await up("报告") == "报告-3"


async def test_doc_binary_roundtrip(client):
    """二进制原样存取（磁盘文件，不经 base64/文本转换）。"""
    await _make_site(client)
    payload = bytes(range(256)) * 4
    files, form = _upload(name="bin", content=payload, filename="a.bin",
                          mime="application/octet-stream")
    doc_id = (await client.post("/api/knowledge/sz-test", files=files, data=form)).json()["id"]
    r = await client.get(f"/api/knowledge/sz-test/{doc_id}/content")
    assert r.content == payload


async def test_doc_size_limit_200mb(fake_platform_redis):
    """200MB 上限：service 层按实际字节复核，超限抛 FileTooLarge。"""
    from backend.app.modules.knowledge import service as ks

    # 直接构造：create_doc 里 _require_site 需要站点存在，先建一个
    from backend.app.modules.sites import service as sites_service
    await sites_service.create_site({"id": "sz-limit", "name": "限流站"})

    ok = b"x" * 10
    await ks.create_doc("sz-limit", {"name": "ok", "filename": "a.bin",
                                     "mime": "application/octet-stream"}, ok)
    with pytest.raises(ks.FileTooLarge):
        await ks.create_doc("sz-limit", {"name": "超限", "filename": "b.bin",
                                         "mime": "application/octet-stream"},
                            b"x" * (ks.MAX_FILE_BYTES + 1))


async def test_doc_rename_only_keeps_file(client):
    """改名不动文件；filename/mime/size 提交被忽略（不可篡改元数据）。"""
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


async def test_delete_site_cascades_metadata(client, fake_platform_redis, tmp_path, monkeypatch):
    """删站连带清元数据 hash 与磁盘目录。"""
    object.__setattr__(settings, "ops_data_dir", str(tmp_path))  # Settings 是 frozen dataclass
    await _make_site(client)
    files, form = _upload(name="手册")
    doc_id = (await client.post("/api/knowledge/sz-test", files=files, data=form)).json()["id"]
    assert await fake_platform_redis.exists(knowledge_key("sz-test"))

    assert (await client.delete("/api/sites/sz-test")).status_code == 204
    assert not await fake_platform_redis.exists(knowledge_key("sz-test"))
    assert not (tmp_path / "knowledge" / "sz-test" / f"{doc_id}.md").exists()


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
