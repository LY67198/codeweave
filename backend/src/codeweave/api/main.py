"""FastAPI app factory — 完整 lifespan + 组件初始化(spec §4.1 / §4.3)。

启动时:
1. 加载 ``Settings`` 单例并塞入 ``app.state.settings``;
2. 幂等 setup PostgresSaver(checkpoint 表);
3. 用 ``anyio.to_thread.run_sync`` 跑 ``_ping_db`` + ``_ping_redis``
   做 DB / Redis warmup,失败立即抛出,启动失败;
4. 实例化 :class:`AuditLogger` / :class:`TokenTracker` / :func:`make_store`
   单例并挂到 ``app.state``;
5. 分配 :class:`OrderedDict` graph_cache(Phase 4 messages router 用);
6. 关闭时 dispose engine 连接池。
"""
from __future__ import annotations

import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable

import anyio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from codeweave.api.errors import register_exception_handlers
from codeweave.api.routers.health import health_router
from codeweave.api.routers.messages import router as messages_router
from codeweave.config.settings import Settings, get_settings
from codeweave.db.base import engine
from codeweave.persistence.audit import AuditLogger
from codeweave.persistence.checkpointer import get_checkpointer
from codeweave.persistence.store import BaseStoreLike, make_store
from codeweave.services.token_tracker import TokenTracker


class TraceIDMiddleware(BaseHTTPMiddleware):
    """提取 / 生成 trace_id 并写到 request.state,响应头回写。"""

    async def dispatch(  # type: ignore[no-untyped-def]
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ):
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


def _ping_db() -> None:
    """同步打开一个 connection 跑 ``SELECT 1``。

    用于 lifespan 启动 warmup,以及 ``/readyz`` 真测。
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def _ping_redis() -> None:
    """同步用 settings.redis_url 建一个短期连接跑 ``PING``。

    socket_connect_timeout=2 防止启动时 Redis 不响应卡死进程。
    """
    import redis

    settings = get_settings()
    r = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
    r.ping()


async def _run_sync(fn: Callable[[], Any]) -> Any:
    """把同步阻塞调用丢到工作线程的薄封装。

    Args:
        fn: 任意无参同步 callable。

    Returns:
        ``fn()`` 的返回值。
    """
    return await anyio.to_thread.run_sync(fn)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan:启动时初始化所有单例,关闭时清理 DB 池。

    启动失败(例如 DB / Redis 不可达)会让 :func:`anyio.to_thread.run_sync`
    把异常重新抛出,FastAPI 在此终止进程,这样 k8s 会重启 pod
    而不是把一个不健康的服务挂上去。
    """
    settings: Settings = get_settings()
    app.state.settings = settings

    # PostgresSaver 幂等 setup(checkpoint 表)
    get_checkpointer().setup()  # type: ignore[no-untyped-call]
    app.state.checkpointer = get_checkpointer()  # type: ignore[no-untyped-call]

    # DB warmup
    await _run_sync(_ping_db)
    app.state.db_engine = engine

    # Redis warmup
    await _run_sync(_ping_redis)

    # 应用单例
    app.state.audit = AuditLogger()
    app.state.token_tracker = TokenTracker()
    app.state.store = make_store()
    app.state.graph_cache = OrderedDict()

    try:
        yield
    finally:
        await _run_sync(engine.dispose)


def build_app() -> FastAPI:
    """构造 FastAPI app,挂载 TraceIDMiddleware + 异常处理器 + health 路由。"""
    app = FastAPI(
        title="CodeWeave API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(TraceIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    register_exception_handlers(app)
    app.include_router(health_router, prefix="")
    app.include_router(messages_router, prefix="/api/v1")
    return app


app = build_app()