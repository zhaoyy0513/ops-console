from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_module_registered_via_register_all():
    """PRD §24.1：模块路由经 register_all 挂载（用 database 扩展性 stub 验证）。"""
    r = client.get("/api/sites/any-site/database/demo")
    assert r.status_code == 200
    assert r.json()["module"] == "database"
