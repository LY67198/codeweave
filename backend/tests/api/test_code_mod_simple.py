"""POST /api/v1/threads/{id}/code-mod SSE 路由测试。

单元层覆盖 4 类:
1. 路由在 OpenAPI schema 中存在(发现性检查)
2. 返回 text/event-stream + done 事件(端到端流程,真实 graph 被 mock)
3. 缺 request field → 422 + ErrorBody
4. 同 thread 第二条 POST 命中 in-flight slot(409 race)

注意:这些测试 mock 路由器内部的 ``_run_coder_review`` 帮助函数,
绕开真实 LangGraph 执行,避免依赖 LLM / DB。但是 422/409 检查仍
需要启动 lifespan,所以会探测 Postgres / Redis — Phase 4 已建好
docker-compose 实例,直接跑即可。
"""
from __future__ import annotations

import json
import time
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from codeweave.api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _collect_sse_events(resp, max_wait: float = 15.0) -> list[dict[str, object]]:
    """把 SSE 响应流解析成 list[dict]。"""
    events: list[dict[str, object]] = []
    deadline = time.time() + max_wait
    for line in resp.iter_lines():
        if time.time() > deadline:
            break
        if not line:
            continue
        if line.startswith("data: "):
            try:
                events.append(json.loads(line.removeprefix("data: ")))
            except json.JSONDecodeError:
                pass
    return events


def test_code_mod_endpoint_exists(client):
    """OpenAPI schema 应含 POST /api/v1/threads/{id}/code-mod。"""
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert any("/code-mod" in p for p in paths)


def test_code_mod_returns_sse_stream(client):
    """端到端跑 /code-mod,expect 至少收到 done 事件。"""
    tid = f"http-codemod-{uuid.uuid4()}"

    # mock 路由器内部的 coder+reviewer 执行函数,绕开真实 LLM / DB 写
    fake_decision = {
        "approved_diff": "--- x.py\n+new\n",
        "final_status": "approved",
        "reviewer_decision": {
            "accept": True,
            "score": 8,
            "feedback": "ok",
            "risk_flags": [],
        },
    }

    with patch(
        "codeweave.api.routers.code_mod._run_coder_review",
        return_value=fake_decision,
    ):
        with client.stream(
            "POST",
            f"/api/v1/threads/{tid}/code-mod",
            json={"request": "add error handling"},
        ) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            events = _collect_sse_events(r, max_wait=15.0)
    kinds = {e["event"] for e in events if e.get("event")}
    assert "done" in kinds


def test_code_mod_validation_422(client):
    """缺 request field → 422 + ErrorBody。"""
    tid = f"bad-{uuid.uuid4()}"
    r = client.post(f"/api/v1/threads/{tid}/code-mod", json={"wrong": "field"})
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"


def test_code_mod_concurrent_409(client):
    """同 thread 第二条 POST 拦截(同 Phase 4 的 in-flight slot)。

    r1 是第一条 stream,故意让 ``_run_coder_review`` 永不返回以保持 active;
    r2 在 r1 进行中发出,应被 409(必须命中 active slot 检查,否则 false
    positive — 即如果先 release 了 slot,则 r2 可能 200,测试不严谨)。
    """
    tid = f"http-codemod-race-{uuid.uuid4()}"

    import threading
    started = threading.Event()
    finish = threading.Event()

    def _blocking_review(*args, **kwargs):
        started.set()
        finish.wait(timeout=10.0)
        return {
            "approved_diff": "--- x.py\n+new\n",
            "final_status": "approved",
            "reviewer_decision": {
                "accept": True,
                "score": 8,
                "feedback": "ok",
                "risk_flags": [],
            },
        }

    def _fire_r1() -> None:
        with client.stream(
            "POST",
            f"/api/v1/threads/{tid}/code-mod",
            json={"request": "blocking"},
        ) as r:
            # 消费 SSE 但不等待结束 — 直到 finish 被 set 才会结束
            for _ in r.iter_lines():
                if finish.is_set():
                    break

    with patch(
        "codeweave.api.routers.code_mod._run_coder_review",
        side_effect=_blocking_review,
    ):
        t1 = threading.Thread(target=_fire_r1)
        t1.start()
        # 等 router 进入 active slot
        assert started.wait(timeout=5.0), "first request never started"

        r2 = client.post(
            f"/api/v1/threads/{tid}/code-mod",
            json={"request": "second"},
        )
        # r2 必须被 409(active stream 冲突)
        assert r2.status_code == 409

        # 释放 r1,让线程清理
        finish.set()
        t1.join(timeout=15.0)
