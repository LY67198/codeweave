"""graph.stream chunk → StreamEvent + SSE 文本格式化(spec §3.6 / §3.1)。"""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from langchain_core.messages import BaseMessage
from langgraph.types import Interrupt

from codeweave.api.models.threads import StreamEvent


def _summarize(value: Any) -> Any:
    """LangChain 消息 / 任意 python 对象 → JSON-safe 字典 / 字符串。

    Args:
        value: 任意 Python 对象(BaseMessage / dict / list / tuple / 标量)。

    Returns:
        JSON-safe 的等价表示。无法序列化的对象回退到 ``repr(value)[:200]`` 截断字符串。
    """
    if isinstance(value, BaseMessage):
        return {
            "type": getattr(value, "type", "message"),
            "content": getattr(value, "content", ""),
        }
    if isinstance(value, dict):
        return {k: _summarize(v) for k, v in value.items() if k != "__interrupt__"}
    if isinstance(value, (list, tuple)):
        return [_summarize(v) for v in value]
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)[:200]


def chunk_to_event(
    chunk: Any,
    *,
    thread_id: str,
    trace_id: str,
) -> StreamEvent:
    """把 LangGraph stream 的单 chunk 翻译成 StreamEvent。

    LangGraph ``stream_mode="updates"`` 产出 ``tuple[node_name, state_update_dict]``。
    形状可能也含 ``__interrupt__`` 列表(若 interrupt 触发)。

    Args:
        chunk: LangGraph 推流的单个 chunk;期望 ``(node_name, state_update_dict)``。
        thread_id: 所属 thread id,会写进 event 上下文。
        trace_id: 贯穿请求追踪 id,会写进 event 上下文。

    Returns:
        对应的 ``StreamEvent``。``__done__`` 节点产生 ``done`` 事件,``__interrupt__`` 产生
        ``hitl_requested``,带 ``messages`` 的产生 ``messages_update``(只含最近 3 条),
        compact 标记产生 ``compact_started`` / ``compact_done``,其余归到 ``node_end``。
    """
    if not isinstance(chunk, tuple) or len(chunk) != 2:
        # 未知 chunk 形态 — fallback
        return StreamEvent(
            event="node_end",
            node=None,
            thread_id=thread_id,
            data={"raw": _summarize(chunk)},
            trace_id=trace_id,
        )

    node, update = chunk[0], chunk[1]
    update = update or {}

    # 内部 done marker — 单独走一条
    if node == "__done__":
        return StreamEvent(
            event="done",
            node=None,
            thread_id=thread_id,
            data={},
            trace_id=trace_id,
        )

    # 处理 interrupt
    interrupts = update.get("__interrupt__")
    if interrupts:
        first: Interrupt = interrupts[0]
        # interrupt.id 由 LangGraph 自动生成;first.id 是稳定 id
        return StreamEvent(
            event="hitl_requested",
            node=node,
            thread_id=thread_id,
            data={
                "interrupt_id": getattr(first, "id", str(uuid4())),
                "tool": first.value.get("tool", "") if isinstance(first.value, dict) else "",
                "args": (
                    first.value.get("command", first.value)
                    if isinstance(first.value, dict)
                    else first.value
                ),
            },
            trace_id=trace_id,
        )

    # 正常节点完成
    has_messages = "messages" in update
    has_compact = "compact_pending" in update or "last_dispatched_compact_id" in update
    if has_messages:
        return StreamEvent(
            event="messages_update",
            node=node,
            thread_id=thread_id,
            data={"messages": _summarize(update["messages"])[-3:]},  # 只发最近 3 条
            trace_id=trace_id,
        )
    if has_compact:
        return StreamEvent(
            event=(
                "compact_done"
                if update.get("compact_pending") is False and update.get("messages")
                else "compact_started"
            ),
            node=node,
            thread_id=thread_id,
            data=_summarize(update),
            trace_id=trace_id,
        )
    return StreamEvent(
        event="node_end",
        node=node,
        thread_id=thread_id,
        data=_summarize(update),
        trace_id=trace_id,
    )


def format_sse(evt: StreamEvent) -> str:
    """把 StreamEvent 序列化成 SSE wire 文本(单条 event,末尾 ``\\n\\n``)。"""
    payload = evt.model_dump(mode="json")
    return f"event: {evt.event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def format_ping(ts_iso: str) -> str:
    """SSE heartbeat(每 15s 由 sse-starlette ping_interval 自动触发)。"""
    return f"event: ping\ndata: {{\"ts\": \"{ts_iso}\"}}\n\n"
