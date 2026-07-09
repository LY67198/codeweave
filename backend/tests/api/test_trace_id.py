"""X-Request-ID 注入 + DI helpers 测试(spec §3.7 / §4.2)。"""
from __future__ import annotations

from fastapi import Depends
from fastapi.testclient import TestClient

from codeweave.api.deps import get_trace_id
from codeweave.api.main import build_app


def _make_app():
    """构造带 /echo 测试端点的 app(base app 已有 health + TraceIDMiddleware)。"""
    test_app = build_app()

    @test_app.api_route("/echo", methods=["GET", "POST"])
    async def echo(trace_id: str = Depends(get_trace_id)) -> dict[str, str]:
        """回显 trace_id 的最小端点,用于测试 DI。"""
        return {"trace_id": trace_id}

    return test_app


client = TestClient(_make_app())


def test_trace_id_from_header_used_directly() -> None:
    """POST /echo with X-Request-ID header → response body has same trace_id."""
    r = client.post("/echo", headers={"X-Request-ID": "trace-from-client-abc"})
    assert r.status_code == 200
    assert r.json()["trace_id"] == "trace-from-client-abc"


def test_trace_id_generated_when_header_missing() -> None:
    """GET /echo without header → trace_id starts with 'trace-'。"""
    r = client.get("/echo")
    assert r.status_code == 200
    tid = r.json()["trace_id"]
    assert tid.startswith("trace-")
    # 长度合理 + 含 uuid hex
    assert len(tid) > 10
    assert "-" in tid


def test_trace_id_in_response_header() -> None:
    """response has X-Request-ID header(回写)。"""
    r = client.get("/echo", headers={"X-Request-ID": "trace-xyz"})
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == "trace-xyz"
