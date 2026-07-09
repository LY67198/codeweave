"""FastAPI 依赖注入 helper(spec §4.2)。"""
from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import Header, Request

from codeweave.config.settings import Settings
from codeweave.persistence.audit import AuditLogger
from codeweave.services.token_tracker import TokenTracker


def get_settings_dep(request: Request) -> Settings:
    """lifespan 中把 settings 存到 app.state,DI 取出。

    Args:
        request: FastAPI 请求对象。

    Returns:
        lifespan 阶段注入到 ``app.state.settings`` 的 Settings 实例。

    Raises:
        AttributeError: lifespan 未运行时取值失败(由调用方在 lifespan 接好后解决)。
    """
    return cast(Settings, request.app.state.settings)


def get_audit(request: Request) -> AuditLogger:
    """lifespan 中把 audit logger 存到 app.state,DI 取出。

    Args:
        request: FastAPI 请求对象。

    Returns:
        lifespan 阶段注入到 ``app.state.audit`` 的 AuditLogger 实例。
    """
    return cast(AuditLogger, request.app.state.audit)


def get_token_tracker(request: Request) -> TokenTracker:
    """lifespan 中把 token tracker 存到 app.state,DI 取出。

    Args:
        request: FastAPI 请求对象。

    Returns:
        lifespan 阶段注入到 ``app.state.token_tracker`` 的 TokenTracker 实例。
    """
    return cast(TokenTracker, request.app.state.token_tracker)


def get_trace_id(
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> str:
    """trace_id 优先从 header 取,否则生成 ``trace-<12 hex>``。

    同时把 trace_id 写到 ``request.state.trace_id`` 让异常处理器可读。

    Args:
        request: FastAPI 请求对象,用于写 request.state.trace_id。
        x_request_id: 客户端传入的 X-Request-ID header 值,可能为空。

    Returns:
        实际用于本次请求的 trace_id 字符串。
    """
    if x_request_id:
        tid = x_request_id
    else:
        tid = f"trace-{uuid.uuid4().hex[:12]}"
    request.state.trace_id = tid
    return tid
