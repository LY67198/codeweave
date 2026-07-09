"""GET /state /timeline /cost 路由测试(spec §2.1)。

需要 Postgres + Redis 在线。
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from codeweave.api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_get_state_after_message(client):
    """先发消息触发 graph,再拉 state — 200 + 包含 ThreadState 字段。"""
    tid = f"queries-{uuid.uuid4()}"
    with client.stream(
        "POST",
        f"/api/v1/threads/{tid}/messages",
        json={"content": "用 read_file 读 backend/src/codeweave/api/main.py 头两行。"},
    ) as r:
        for _ in r.iter_lines():
            pass

    r = client.get(f"/api/v1/threads/{tid}/state")
    assert r.status_code == 200
    body = r.json()
    assert body["thread_id"] == tid
    assert isinstance(body["messages"], list)
    assert isinstance(body["todos"], list)
    assert "compact_pending" in body
    assert "plan_mode" in body


def test_get_state_returns_404_for_unknown_thread(client):
    """未知 thread 应 404 + code=not_found。"""
    r = client.get(f"/api/v1/threads/never-existed-{uuid.uuid4()}/state")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == "not_found"


def test_get_timeline_returns_events_list(client):
    """先触发一些 audit 事件,再拉 timeline — 200 + events 数组。"""
    tid = f"queries-{uuid.uuid4()}"
    with client.stream(
        "POST",
        f"/api/v1/threads/{tid}/messages",
        json={"content": "读 backend/src/codeweave/api/main.py,简短回答。"},
    ) as r:
        for _ in r.iter_lines():
            pass
    r = client.get(f"/api/v1/threads/{tid}/timeline")
    assert r.status_code == 200
    body = r.json()
    assert body["thread_id"] == tid
    assert isinstance(body["events"], list)


def test_get_cost_returns_by_model(client):
    """GET /cost — 200 + 包含 by_model / since 字段。"""
    r = client.get("/api/v1/cost")
    assert r.status_code == 200
    body = r.json()
    assert "by_model" in body
    assert "since" in body
    assert isinstance(body["by_model"], dict)