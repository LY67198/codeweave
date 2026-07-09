"""graph.stream chunk → StreamEvent + SSE 文本格式化(spec §3.6 / §3.1)。

LangGraph ``stream_mode="updates"`` 实际产出形态(已验证):
- 单节点流结束:``{"<node_name>": <state_update_dict>}``
  例:``{"executor": {"messages": [HumanMessage(...)]}}``
- interrupt:``{"__interrupt__": (Interrupt(...),)}``
- 内部 sentinel(由 ``_stream_graph`` 插入):``("__done__", {})``

本模块同时支持 tuple-shape 形态以保留 ``test_sse_format.py`` 既有断言。
"""
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


def _handle_hitl(
    node: str | None,
    interrupts: tuple[Any, ...],
    *,
    thread_id: str,
    trace_id: str,
) -> StreamEvent:
    """统一处理 hitl_requested event — 不管 chunk 是 dict or tuple 形态。"""
    first: Interrupt = interrupts[0]
    value = first.value
    return StreamEvent(
        event="hitl_requested",
        node=node or "tools",
        thread_id=thread_id,
        data={
            "interrupt_id": getattr(first, "id", str(uuid4())),
            "tool": value.get("tool", "") if isinstance(value, dict) else "",
            "args": (
                value.get("command", value)
                if isinstance(value, dict)
                else value
            ),
        },
        trace_id=trace_id,
    )


def _handle_state_update(
    node: str,
    update: dict[str, Any],
    *,
    thread_id: str,
    trace_id: str,
) -> StreamEvent:
    """根据 update dict 内容映射到具体 event 类型。"""
    has_messages = "messages" in update
    has_compact = "compact_pending" in update or "last_dispatched_compact_id" in update

    if has_messages:
        return StreamEvent(
            event="messages_update",
            node=node,
            thread_id=thread_id,
            data={"messages": _summarize(update["messages"])[-3:]},
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


def chunk_to_event(
    chunk: Any,
    *,
    thread_id: str,
    trace_id: str,
) -> StreamEvent:
    """把 LangGraph stream 的单 chunk 翻译成 StreamEvent。

    支持三种形态(LangGraph 实际产出 + 内部 sentinel):
    - ``{"__interrupt__": (Interrupt(...),)}`` → hitl_requested
    - ``{"<node_name>": <state_update>}`` → node_end / messages_update / compact_*
    - ``("__done__", {})`` → done
    - ``(<node_name>, <state_update>)`` → 同上(tuple shape,保留兼容测试)
    """
    # 形态 1: dict,sse-starlette 真输出形态
    if isinstance(chunk, dict):
        # interrupt 优先
        if "__interrupt__" in chunk:
            interrupts = chunk["__interrupt__"]
            if interrupts:
                return _handle_hitl(
                    node=None,
                    interrupts=interrupts,
                    thread_id=thread_id,
                    trace_id=trace_id,
                )
        # 普通节点流结束 — dict 通常只有一个 key
        for node, raw_update in chunk.items():
            if node.startswith("__"):
                continue  # skip __interrupt__ / __metadata__ 等内部 key
            update = raw_update if isinstance(raw_update, dict) else {"value": raw_update}
            return _handle_state_update(
                node=node,
                update=update or {},
                thread_id=thread_id,
                trace_id=trace_id,
            )
        # 空 dict 或只剩内部 key — fallback
        return StreamEvent(
            event="node_end",
            node=None,
            thread_id=thread_id,
            data={"raw": _summarize(chunk)},
            trace_id=trace_id,
        )

    # 形态 2: tuple(本模块生成 sentinel 或旧测试用)
    if isinstance(chunk, tuple) and len(chunk) == 2:
        node, update = chunk[0], chunk[1] or {}
        if node == "__done__":
            return StreamEvent(
                event="done",
                node=None,
                thread_id=thread_id,
                data={},
                trace_id=trace_id,
            )
        interrupts = update.get("__interrupt__") if isinstance(update, dict) else None
        if interrupts:
            return _handle_hitl(
                node=node,
                interrupts=interrupts,
                thread_id=thread_id,
                trace_id=trace_id,
            )
        if isinstance(update, dict):
            return _handle_state_update(
                node=node,
                update=update,
                thread_id=thread_id,
                trace_id=trace_id,
            )

    # 形态未知 — fallback
    return StreamEvent(
        event="node_end",
        node=None,
        thread_id=thread_id,
        data={"raw": _summarize(chunk)},
        trace_id=trace_id,
    )


def format_sse(evt: StreamEvent) -> str:
    """把 StreamEvent 序列化成 SSE wire 文本(单条 event,末尾 ``\\n\\n``)。"""
    payload = evt.model_dump(mode="json")
    return f"event: {evt.event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def format_ping(ts_iso: str) -> str:
    """SSE heartbeat(每 15s 由 sse-starlette ping 自动触发)。"""
    payload = json.dumps({"ts": ts_iso}, ensure_ascii=False)
    return f"event: ping\ndata: {payload}\n\n"
