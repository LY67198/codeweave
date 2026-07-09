"""HITL approve / deny 路径测试(spec §2.1 / §3.5 / §5.1)。

通过 monkeypatch executor 模型返回一个 ``run_bash`` tool_call(危险命令),
触发 ``interrupt()`` → 走 /resume → graph 自然结束,验证 ``done`` 事件。
无需真实 LLM,纯本地 fastapi TestClient + LangGraph InMemorySaver。
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from codeweave.api.main import app


@pytest.fixture
def client(monkeypatch):
    """用 InMemorySaver + mock LLM 替换 lifespan 默认 PostgresSaver。

    executor_node 调 ``_get_executor_model()``(lru_cache 1);第二次起直接
    命中 cache,monkeypatch 要在 lru_cache 命中前注入。TestClient(app) 进
    入 lifespan 时 graph_cache 仍为空,所以 ``_get_compiled_graph`` 会构
    造图,但我们用单独的 InMemorySaver 替换 checkpointer。
    """
    from codeweave.api.routers import messages as messages_module

    # 替换 PostgresSaver 为 InMemorySaver
    in_mem = InMemorySaver()

    # mock executor 模型:返回一个带 tool_call 的 AIMessage
    mock_model = MagicMock()
    fake_ai = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call_test_bash",
                "name": "run_bash",
                "args": {"command": "echo rm -rf /tmp/codeweave-dummy-test"},
            }
        ],
    )
    mock_model.invoke.return_value = fake_ai

    # bind_tools 返回的 mock(我们的 executor_node 用 ``bind_tools``)
    mock_bound = MagicMock()
    mock_bound.invoke.return_value = fake_ai
    mock_model.bind_tools.return_value = mock_bound

    # 重新构造 graph_cache,使用 InMemorySaver,并把 executor 模型的 cache 失效
    from codeweave.agents import executor as executor_module
    executor_module._get_executor_model.cache_clear()

    monkeypatch.setattr(executor_module, "_get_executor_model", lambda: mock_model)

    with TestClient(app) as c:
        # 替换 checkpointer 为 InMemorySaver
        c.app.state.checkpointer = in_mem
        yield c


def _read_sse_events(resp, max_wait=30.0):
    """把 SSE 响应流解析成 list[dict]。"""
    events: list[dict[str, Any]] = []
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


def test_hitl_approve_flow(client):
    """approve 路径:hitl_requested → resume approve → 流结束有 done 事件。"""
    tid = f"hitl-{uuid.uuid4()}"
    with client.stream(
        "POST",
        f"/api/v1/threads/{tid}/messages",
        json={"content": "执行 rm -rf /tmp/codeweave-dummy-test"},
    ) as r:
        assert r.status_code == 200
        events = _read_sse_events(r, max_wait=60)
    hitl = [e for e in events if e.get("event") == "hitl_requested"]
    assert len(hitl) == 1, (
        f"expected hitl_requested, got {[e.get('event') for e in events]}"
    )
    interrupt_id = hitl[0]["data"]["interrupt_id"]
    assert interrupt_id

    # approve(使用 bash_tools 期待的 ``approved`` 字段名)
    with client.stream(
        "POST",
        f"/api/v1/threads/{tid}/resume",
        json={"interrupt_id": interrupt_id, "decision": {"approved": True}},
    ) as r:
        assert r.status_code == 200
        events2 = _read_sse_events(r, max_wait=60)
    kinds = {e["event"] for e in events2}
    assert "done" in kinds


def test_hitl_deny_flow(client):
    """deny 路径:hitl_requested → resume deny → 流结束有 done 事件。"""
    tid = f"hitl-{uuid.uuid4()}"
    with client.stream(
        "POST",
        f"/api/v1/threads/{tid}/messages",
        json={"content": "执行 rm -rf /tmp/codeweave-dummy-test"},
    ) as r:
        events = _read_sse_events(r, max_wait=60)
    hitl = [e for e in events if e.get("event") == "hitl_requested"]
    assert hitl, "expected hitl_requested"
    interrupt_id = hitl[0]["data"]["interrupt_id"]

    with client.stream(
        "POST",
        f"/api/v1/threads/{tid}/resume",
        json={"interrupt_id": interrupt_id, "decision": {"approved": False}},
    ) as r:
        events2 = _read_sse_events(r, max_wait=60)
    kinds = {e["event"] for e in events2}
    assert "done" in kinds