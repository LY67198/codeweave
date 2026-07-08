"""Audit 日志层(spec §5.2)。

- :class:`AuditLogger` 单进程可创建多实例,共享同一 Session 工厂。
- :func:`audit_span` 上下文管理器,自动捕获开始 / 结束事件。
- 写入失败吞掉异常,业务继续(spec §5.3,§7)。
"""
from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from codeweave.db.base import get_session
from codeweave.db.models import AuditEvent

logger = logging.getLogger(__name__)


class _SessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AuditLogger:
    """审计日志写入器。"""

    def __init__(self, session_factory: _SessionFactory | None = None) -> None:
        self._factory: _SessionFactory = session_factory or get_session

    def emit(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        thread_id: str,
        duration_ms: int | None = None,
    ) -> None:
        """同步写一行 audit_events。失败仅 logger.error,不抛。"""
        try:
            row = AuditEvent(
                thread_id=thread_id,
                kind=kind,
                payload=payload,
                duration_ms=duration_ms,
            )
            with self._factory() as session:
                session.add(row)
                session.commit()
        except SQLAlchemyError as exc:
            logger.error("audit_emit_failed", extra={"kind": kind, "error": str(exc)})

    def get_thread_timeline(self, thread_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """按时间线拉取某 thread 最近 N 条事件。

        按时间正序(早→晚)返回事件列表,便于前端 timeline 渲染。
        """
        with self._factory() as session:
            stmt = (
                select(AuditEvent)
                .where(AuditEvent.thread_id == thread_id)
                .order_by(AuditEvent.ts.asc())
                .limit(limit)
            )
            scalars = session.execute(stmt).scalars().all()
            return [
                {
                    "id": r.id,
                    "ts": r.ts,
                    "kind": r.kind,
                    "payload": r.payload,
                    "duration_ms": r.duration_ms,
                }
                for r in scalars
            ]


@contextmanager
def audit_span(
    audit_logger: AuditLogger,
    kind: str,
    *,
    thread_id: str,
    extra_payload: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """上下文管理器,记录 node 进入 / 退出 + duration_ms。

    Yields:
        用于 with 块内增量更新 payload 的 dict(可修改)。
    """
    payload: dict[str, Any] = dict(extra_payload or {})
    start = dt.datetime.now(dt.timezone.utc)
    audit_logger.emit(f"{kind}_enter", payload, thread_id=thread_id)
    try:
        yield payload
    finally:
        elapsed = (dt.datetime.now(dt.timezone.utc) - start).total_seconds() * 1000
        payload["duration_ms"] = int(elapsed)
        audit_logger.emit(f"{kind}_exit", payload, thread_id=thread_id)


def audit_tool(
    audit_logger: AuditLogger,
    tool_name_getter: Callable[..., str],
) -> Callable[..., Any]:
    """装饰器工厂:装饰 tool 函数,自动 emit tool_call 事件。"""
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            import time
            start = time.monotonic()
            thread_id = kwargs.get("thread_id", "<no-thread>")
            try:
                result = fn(*args, **kwargs)
                duration_ms = int((time.monotonic() - start) * 1000)
                audit_logger.emit(
                    "tool_call",
                    {
                        "tool": tool_name_getter(*args, **kwargs),
                        "args": _safe_args_repr(args, kwargs),
                        "result_summary": _result_summary(result),
                    },
                    thread_id=thread_id,
                    duration_ms=duration_ms,
                )
                return result
            except Exception as exc:
                duration_ms = int((time.monotonic() - start) * 1000)
                audit_logger.emit(
                    "tool_call",
                    {
                        "tool": tool_name_getter(*args, **kwargs),
                        "args": _safe_args_repr(args, kwargs),
                        "error": str(exc),
                    },
                    thread_id=thread_id,
                    duration_ms=duration_ms,
                )
                raise

        return wrapper
    return decorator


def _safe_args_repr(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    return {"args": list(args), "kwargs": {k: repr(v)[:200] for k, v in kwargs.items()}}


def _result_summary(result: Any) -> str:
    s = repr(result)
    return s[:200] if isinstance(result, str) else repr(result)[:200]
