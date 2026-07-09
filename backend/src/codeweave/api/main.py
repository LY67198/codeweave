"""FastAPI app factory(spec §4.3)。

lifespan 在 Task 6 完善,本 task 加 TraceIDMiddleware。
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from codeweave.api.errors import register_exception_handlers
from codeweave.api.routers.health import health_router


class TraceIDMiddleware(BaseHTTPMiddleware):
    """提取 / 生成 trace_id 并写到 request.state,响应头回写。"""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        """从 header 提取 trace_id,缺失则生成,响应头回写。

        Args:
            request: 入站 HTTP 请求。
            call_next: 下一个 ASGI handler。

        Returns:
            带有 X-Request-ID header 的响应。
        """
        tid = request.headers.get("X-Request-ID") or f"trace-{uuid.uuid4().hex[:12]}"
        request.state.trace_id = tid
        response = await call_next(request)
        response.headers["X-Request-ID"] = tid
        return response


def build_app() -> FastAPI:
    """构造 FastAPI app,挂载 TraceIDMiddleware + 异常处理器 + health 路由。"""
    app = FastAPI(
        title="CodeWeave API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router, prefix="")
    return app


app = build_app()
