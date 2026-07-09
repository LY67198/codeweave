"""ErrorBody + 全局异常处理器测试(spec §2.4)。"""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from codeweave.api.errors import (
    ApiError,
    ErrorBody,
    register_exception_handlers,
)

app = FastAPI()
register_exception_handlers(app)


@app.get("/http-exc")
async def http_exc():
    raise HTTPException(status_code=404, detail="not_found")


@app.get("/api-exc")
async def api_exc():
    raise ApiError(code="bad_state", message="graph not ready", status_code=409)


@app.get("/unexpected")
async def unexpected():
    raise RuntimeError("boom")


client = TestClient(app, raise_server_exceptions=False)


def test_http_exception_uses_error_body_shape():
    r = client.get("/http-exc")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == "not_found"
    assert "trace_id" in body


def test_api_exception_custom_code():
    r = client.get("/api-exc")
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "bad_state"
    assert body["message"] == "graph not ready"
    assert "trace_id" in body


def test_validation_error_pydantic_default_uses_422():
    @app.post("/v")
    async def v(x: int):
        return x

    r = client.post("/v", json={})  # x 缺失
    assert r.status_code == 422
