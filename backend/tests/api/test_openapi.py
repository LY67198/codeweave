"""OpenAPI schema + 路由数检查(spec §5.1 DoD #9 / #10)。"""
from fastapi.testclient import TestClient

from codeweave.api.main import app


def test_openapi_lists_two_post_routes():
    with TestClient(app) as c:
        schema = c.get("/openapi.json").json()
    post_paths = [p for p, ops in schema["paths"].items()
                  if "post" in ops]
    assert any("/messages" in p for p in post_paths)
    assert any("/resume" in p for p in post_paths)


def test_openapi_lists_four_get_routes():
    with TestClient(app) as c:
        schema = c.get("/openapi.json").json()
    get_paths = [p for p, ops in schema["paths"].items()
                 if "get" in ops]
    # /healthz + /readyz + /state + /timeline + /cost = 5
    assert any("/healthz" in p for p in get_paths)
    assert any("/readyz" in p for p in get_paths)
    assert any("/state" in p for p in get_paths)
    assert any("/timeline" in p for p in get_paths)
    assert any("/cost" in p for p in get_paths)


def test_env_values_not_in_openapi():
    """Pydantic models 没有暴露 OPENAI_API_KEY 等值。"""
    with TestClient(app) as c:
        schema = c.get("/openapi.json").json()
    # 序列化整个 schema,看有没有 key 字符串
    import json
    text_blob = json.dumps(schema)
    assert "sk-" not in text_blob   # 任何 API key 都不应该出现
    # OPENAI_API_KEY 字段不应该在 components.schemas 里
    schemas = schema.get("components", {}).get("schemas", {})
    assert "OpenaiApiKey" not in str(schemas)
    assert "Settings" not in schemas  # Settings 模型整体不导出


def test_route_summary_present():
    with TestClient(app) as c:
        schema = c.get("/openapi.json").json()
    # 每个路由都应该有 summary
    for path, ops in schema["paths"].items():
        for method, op in ops.items():
            assert "summary" in op, f"{method.upper()} {path} missing summary"