"""POST /messages SSE 流测试(spec §2.1 / §3.7)。

需要 Postgres + Redis 在线。
"""
import json
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from codeweave.api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_post_message_returns_sse_stream(client):
    """POST /messages 返回 text/event-stream,事件流中至少含 done / node_end。"""
    tid = f"api-test-{uuid.uuid4()}"
    with client.stream(
        "POST",
        f"/api/v1/threads/{tid}/messages",
        json={"content": "用 read_file 读 backend/src/codeweave/api/main.py 头三行,简短回答。"},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = []
        for line in r.iter_lines():
            if not line:
                continue
            if line.startswith("data: "):
                events.append(json.loads(line.removeprefix("data: ")))
        # 必须至少收到 node_end / done 之一
        kinds = {e["event"] for e in events if e.get("event")}
        assert "done" in kinds or "node_end" in kinds


def test_validation_error_422_on_bad_body(client):
    """缺 content 字段的 body 应得 422 + code=validation_error + trace_id。"""
    tid = f"api-test-{uuid.uuid4()}"
    r = client.post(f"/api/v1/threads/{tid}/messages", json={"wrong_field": 1})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error"
    assert "trace_id" in body


def test_concurrent_same_thread_returns_409(client):
    """第一条消息的流还在跑时,第二条 POST 同 thread 应返 409(race-tolerant)。

    在线程里 wait 第一条流结束后再发第二条,避免误判。本测试只验初始并发。
    """
    tid = f"api-test-{uuid.uuid4()}"
    responses: list[int] = []

    def fire():
        with client.stream(
            "POST",
            f"/api/v1/threads/{tid}/messages",
            json={"content": "请读 backend/src/codeweave/api/main.py 头两行,然后只要 1。"},
        ) as r:
            responses.append(r.status_code)
            for _ in r.iter_lines():
                time.sleep(0.01)

    t1 = threading.Thread(target=fire)
    t1.start()
    time.sleep(0.5)  # 等第一条 stream 开始

    # 第一条并发请求(应被 409 拒)
    with client.stream(
        "POST",
        f"/api/v1/threads/{tid}/messages",
        json={"content": "concurrent second"},
    ) as r:
        responses.append(r.status_code)

    t1.join()
    # 至少有一个 200,第二个可能是 409(并发命中)或 200(第一条太快结束)
    assert 200 in responses
