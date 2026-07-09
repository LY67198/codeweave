"""健康检查路由测试(spec §2.1 / §4.3)— Phase 4 版本需要真 Postgres + Redis。"""
import pytest
from fastapi.testclient import TestClient

from codeweave.api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:  # 触发 lifespan
        yield c


def test_healthz_returns_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_returns_ready_when_db_and_redis_up(client):
    """需要 Docker 跑着 postgres + redis;本地 docker compose up -d 应当通过。"""
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert "checks" in body
    assert body["checks"]["postgres"] == "ok"
    assert body["checks"]["redis"] == "ok"


def test_openapi_lists_health_endpoints():
    with TestClient(app) as c:
        schema = c.get("/openapi.json").json()
    assert "/healthz" in schema["paths"]
    assert "/readyz" in schema["paths"]