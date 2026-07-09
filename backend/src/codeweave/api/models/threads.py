"""thread / message / HITL / SSE stream 相关模型(spec §2.3)。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """统一 UTC 时间戳(避免 timezone-naive datetime)。"""
    return datetime.now(tz=timezone.utc)


class HumanMessageIn(BaseModel):
    """POST /threads/{id}/messages 请求体。"""
    content: str = Field(..., max_length=32000, description="user 消息正文")
    role: Literal["human"] = Field(default="human", description="Phase 4 仅支持 human")


class ResumeIn(BaseModel):
    """POST /threads/{id}/resume 请求体 — HITL 决策回传。"""
    interrupt_id: str = Field(..., description="对应最近一次 hitl_requested event 的 id")
    decision: dict[str, Any] = Field(
        default_factory=dict,
        description="透传给 Command(resume=...); 常见 shape: {\"approve\": true|false}",
    )


class StreamEvent(BaseModel):
    """SSE 一条事件 payload(经 ``data: <json>`` 字段传出)。"""
    event: Literal[
        "node_start", "node_end", "messages_update",
        "tool_call", "tool_result",
        "compact_started", "compact_done",
        "hitl_requested", "done", "error",
    ] = Field(..., description="事件类型")
    node: str | None = Field(default=None, description="哪个节点产出")
    thread_id: str = Field(..., description="所属 thread")
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)
    trace_id: str = Field(..., description="贯穿请求追踪 id")


class ThreadState(BaseModel):
    """GET /threads/{id}/state 响应 — 当前 checkpoint 全量。"""
    thread_id: str
    messages: list[dict[str, Any]]
    todos: list[dict[str, Any]]
    plan_mode: bool
    agent_history: list[dict[str, Any]]
    compact_pending: bool
    last_dispatched_compact_id: str | None


class TimelineResponse(BaseModel):
    """GET /threads/{id}/timeline 响应 — audit_events 倒序时间线。"""
    thread_id: str
    events: list[dict[str, Any]] = Field(default_factory=list)
