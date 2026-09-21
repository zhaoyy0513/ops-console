from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_demo_module_registered():
    """PRD §24.1：模块路由经 register_all 挂载。"""
    r = client.get("/api/demo")
    assert r.status_code == 200
    assert r.json() == {"module": "demo", "status": "ok"}
