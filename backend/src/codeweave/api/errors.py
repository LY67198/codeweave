"""统一错误体 + 全局异常处理器(spec §2.3 / §2.4)。"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    """统一错误响应 schema(spec §2.4)。"""
    code: str = Field(..., description="稳定错误码(业务/协议级)")
    message: str = Field(..., description="人类可读错误描述")
    trace_id: str = Field(..., description="贯穿请求追踪 id")
    details: dict[str, Any] | None = Field(default=None, description="可选附加上下文")


class ApiError(Exception):
    """业务层异常,由 router 显式 raise,异常处理器统一序列化。"""
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


def _trace_id(req: Request) -> str:
    return getattr(req.state, "trace_id", "trace-unknown")


def error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    trace_id: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = {"code": code, "message": message, "trace_id": trace_id, "details": details}
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    """把 FastAPI 默认的 exception 响应格式统一为 ErrorBody。"""

    @app.exception_handler(HTTPException)
    async def _http_exc(req: Request, exc: HTTPException) -> JSONResponse:
        code = _http_code_to_api_code(exc.status_code, exc.detail)
        return error_response(
            code=code,
            message=str(exc.detail),
            status_code=exc.status_code,
            trace_id=_trace_id(req),
        )

    @app.exception_handler(ApiError)
    async def _api_exc(req: Request, exc: ApiError) -> JSONResponse:
        return error_response(
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            trace_id=_trace_id(req),
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def _val_exc(req: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            code="validation_error",
            message="request body or params invalid",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            trace_id=_trace_id(req),
            details={"errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def _unhandled(req: Request, exc: Exception) -> JSONResponse:
        # 未预期异常 — log 详尽信息,但对外屏蔽内部细节
        logger.exception("unhandled_exception", extra={"trace_id": _trace_id(req)})
        return error_response(
            code="internal_error",
            message="internal error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            trace_id=_trace_id(req),
        )


def _http_code_to_api_code(http_code: int, detail: Any) -> str:
    """把 FastAPI HTTPException(detail=...) 转成稳定的 code 字符串。"""
    if isinstance(detail, str):
        return detail
    mapping = {
        400: "bad_request",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        503: "service_unavailable",
    }
    return mapping.get(http_code, f"http_{http_code}")
