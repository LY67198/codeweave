"""通过 FastAPI HTTP 跑一次真实 LLM compact 闭环(spec §5.3)。"""
from __future__ import annotations

import json
import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError, OperationalError


def _postgres_reachable(url: str, timeout: float = 2.0) -> bool:
    """短超时探测 Postgres 是否可达,避免测试集卡死。"""
    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(
            url,
            connect_args={"connect_timeout": int(timeout)},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (OperationalError, DBAPIError, OSError, ValueError):
        return False


@pytest.fixture(autouse=True)
def require_postgres():
    """若没有可用的 postgres 则跳过整个 e2e。"""
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url:
        pytest.skip("DATABASE_URL not set to a postgres URL")
    if not _postgres_reachable(url):
        pytest.skip(f"Postgres not reachable at {url}")


@pytest.fixture(autouse=True)
def require_real_llm_key():
    """若没有真实的 OPENAI_API_KEY / OPENAI_BASE_URL 则跳过。

    conftest 默认 set 了 ``sk-test`` 占位,这里判断是否为真 key。
    """
    key = os.environ.get("OPENAI_API_KEY", "")
    base = os.environ.get("OPENAI_BASE_URL", "")
    if not key or key == "sk-test" or "example.invalid" in base:
        pytest.skip(
            "OPENAI_API_KEY / OPENAI_BASE_URL not configured for real LLM "
            "(conftest 占位,跳过)"
        )


@pytest.fixture(autouse=True)
def require_redis():
    """若 Redis 不可达则跳过(API lifespan warmup 会卡住)。"""
    import redis

    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        r = redis.Redis.from_url(url, socket_connect_timeout=2)
        r.ping()
    except Exception as exc:
        pytest.skip(f"Redis not reachable at {url}: {exc}")


def _collect_sse_events(resp, max_wait):
    """从 SSE response 里抽出 ``data: ...`` JSON 行,直到流结束或超时。

    Args:
        resp: ``httpx.Response``(由 ``TestClient.stream(...)`` 产出)。
        max_wait: 最长等待秒数。

    Returns:
        解析出的 event 字典列表(已 JSON 解码的 ``data`` payload)。
    """
    events = []
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


@pytest.mark.llm
def test_real_compact_roundtrip_via_http():
    """需要 Postgres + Redis + 真 DeepSeek API key(在 .env)。"""
    # 用 TestClient 必须 enter lifespan
    with TestClient(app) as c:
        tid = f"http-real-llm-{uuid.uuid4()}"
        # 用足够长的消息触发 compact
        long_content = (
            "CodeWeave 是一个 LangGraph 多 Agent 编码助手。" * 30
        )

        # 一条消息触发 dispatch
        with c.stream("POST", f"/api/v1/threads/{tid}/messages",
                      json={"content": long_content}) as r:
            assert r.status_code == 200
            events_a = _collect_sse_events(r, max_wait=30)
        # 验证 dispatch 路径走过(node_end data.kind="dispatch",或流末 done 事件)
        actions = [e.get("data", {}).get("kind") for e in events_a
                   if e.get("event") == "node_end"]
        assert "dispatch" in actions or "done" in {e["event"] for e in events_a}

        # 第二轮 state 应已经更新
        state = c.get(f"/api/v1/threads/{tid}/state").json()
        assert state["thread_id"] == tid

        # 第三轮:再发一条让 compact apply 进 messages
        with c.stream("POST", f"/api/v1/threads/{tid}/messages",
                      json={"content": "test apply", "role": "human"}) as r:
            for _ in r.iter_lines():
                pass


# 在 fixture 之后 import app(避免 conftest 还没 patch OPENAI_API_KEY 之前 app 跑起来)
from codeweave.api.main import app  # noqa: E402