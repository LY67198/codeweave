"""FastAPI app factory(spec §4.3)。

lifespan 在 Task 9 完善,本 task 只放最简骨架。"""
from __future__ import annotations

from fastapi import FastAPI

from codeweave.api.routers.health import health_router


def build_app() -> FastAPI:
    app = FastAPI(
        title="CodeWeave API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.include_router(health_router, prefix="")
    return app


app = build_app()