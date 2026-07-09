"""通过 HTTP 跑真 DeepSeek LLM 走完整 Maker/Checker 闭环。

需要:Postgres + Redis + 真 DeepSeek API key(在 .env)。
本测试默认 skip,运行时加 ``-m llm``。
"""
from __future__ import annotations

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from codeweave.api.main import app


@pytest.mark.llm
def test_real_code_mod_roundtrip_via_http():
    """需要:Postgres + Redis + 真 DeepSeek API key。

    跑一次 ``POST /api/v1/threads/{tid}/code-mod`` 端到端,期望
    Coder 用 write_file 产 diff,Reviewer 给决策,router 把
    ``reviewer_decision`` 折进 ``done`` 事件。
    """
    with TestClient(app) as c:
        tid = f"http-real-codemod-{uuid.uuid4()}"
        with c.stream(
            "POST",
            f"/api/v1/threads/{tid}/code-mod",
            json={
                "request": (
                    "Create a new file backend/src/codeweave/api/routers/echo.py "
                    "containing one FastAPI route POST /echo that accepts "
                    '{"message": "hello"} and returns {"message": "olleh"} '
                    "(reversed string). Include a Pydantic v2 model EchoIn. "
                    "Use write_file to create the file. Do not touch any other file."
                ),
            },
        ) as r:
            assert r.status_code == 200
            events = _collect(r, max_wait=120)

    kinds = {e.get("event") for e in events if e.get("event")}
    # 期望事件链:codermod 流:
    #   coder → reviewer(可能 retry)→ ... → finalize → done
    assert "done" in kinds
    # 应该至少经历 1 轮 review(看到 reviewer_decision 在 done.data 中)
    done_events = [e for e in events if e.get("event") == "done"]
    assert done_events, "no done event received"
    done_data = done_events[-1].get("data") or {}
    assert "reviewer_decision" in done_data, (
        f"expected reviewer_decision in done.data, got keys={list(done_data.keys())}"
    )


def _collect(resp, max_wait):
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