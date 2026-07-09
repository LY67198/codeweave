"""健康检查 + ready 路由(spec §2.1 / §4.3)。

``/healthz`` 是纯进程级 liveness,不依赖外部 — k8s liveness probe
应打这个,避免 DB 短暂抖动把 pod 重启掉。

``/readyz`` 是 readiness,真实检查 Postgres + Redis;任一依赖不可达
就抛 :class:`ApiError`(503),k8s readiness probe 收到非 200 会把流量
从该 pod 摘掉。
"""
from __future__ import annotations

from typing import Any

import redis
from fastapi import APIRouter, Depends, Request

from codeweave.api.deps import get_settings_dep
from codeweave.api.errors import ApiError
from codeweave.config.settings import Settings

health_router = APIRouter(tags=["health"])


@health_router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    """k8s liveness — 进程还活着就返回 ok,不依赖外部服务。

    Returns:
        ``{"status": "ok"}``
    """
    return {"status": "ok"}


@health_router.get("/readyz", summary="Readiness probe")
async def readyz(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    """k8s readiness — DB + Redis 都可达才 ready,否则 503。

    ``_ping_db`` 从 :mod:`codeweave.api.main` 导入以避免循环 import
    (main.py 已经依赖 routers)。

    Args:
        request: FastAPI 请求对象(用于 trace_id / app state 读取)。
        settings: 来自 DI 的 Settings 实例。

    Returns:
        ``{"status": "ready", "checks": {"postgres": "ok", "redis": "ok"}}``

    Raises:
        ApiError: 任一依赖检查失败时抛 503 ``service_unavailable``,
            ``details`` 里包含每个 check 的状态字符串。
    """
    from codeweave.api.main import _ping_db, _run_sync  # 避免循环 import

    checks: dict[str, str] = {}

    try:
        await _run_sync(_ping_db)
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"fail: {exc.__class__.__name__}"

    try:
        r = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        await _run_sync(r.ping)
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"fail: {exc.__class__.__name__}"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        raise ApiError(
            code="service_unavailable",
            message="dependency check failed",
            status_code=503,
            details=checks,
        )
    return {"status": "ready", "checks": checks}