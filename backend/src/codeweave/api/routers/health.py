"""健康检查 + ready 路由(spec §2.1)。"""
from __future__ import annotations

from fastapi import APIRouter

health_router = APIRouter(tags=["health"])


@health_router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    """k8s liveness — 进程还活着就返回 ok,不依赖外部服务。

    Returns:
        ``{"status": "ok"}``
    """
    return {"status": "ok"}


@health_router.get("/readyz", summary="Readiness probe")
async def readyz() -> dict[str, str]:
    """k8s readiness — DB + Redis 可达才返回 ready。

    Task 9 接 lifespan 后真做 DB ping + Redis PING。Phase 4 起步先返回 ready。
    """
    return {"status": "ready"}