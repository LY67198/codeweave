"""健康检查路由测试(spec §2.1 / §4.3)。"""
from fastapi.testclient import TestClient

from codeweave.api.main import app


def test_healthz_returns_ok():
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_returns_ready_when_db_up():
    client = TestClient(app)
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_openapi_lists_health_endpoints():
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    assert "/healthz" in schema["paths"]
    assert "/readyz" in schema["paths"]