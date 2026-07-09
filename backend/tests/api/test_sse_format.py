"""graph.stream chunk → StreamEvent 转换器测试(spec §3.1 / §3.6)。"""
from __future__ import annotations

import json

from langgraph.types import Interrupt

from codeweave.api.models.threads import StreamEvent
from codeweave.api.sse import chunk_to_event, format_sse


def test_node_end_chunk_translates_to_event():
    # LangGraph updates-mode chunk: (node_name, state_update_dict)
    # 没有 messages / __interrupt__ / compact_* 字段时归到 node_end
    chunk = ("executor", {"_agent_history": ["h1"], "todos": []})
    evt = chunk_to_event(chunk, thread_id="t-1", trace_id="trace-1")
    assert isinstance(evt, StreamEvent)
    assert evt.event == "node_end"
    assert evt.node == "executor"
    assert evt.thread_id == "t-1"
    assert evt.trace_id == "trace-1"
    # _summarize 应透传普通 dict 字段
    assert "_agent_history" in evt.data
    assert evt.data["_agent_history"] == ["h1"]


def test_interrupt_chunk_translates_to_hitl_requested():
    # LangGraph interrupt 形态(具体 shape 在 Lifespan + run 时验证)
    interrupt_value = Interrupt(value={"prompt": "approve?", "tool": "run_bash", "command": "rm /"})
    chunk = ("executor", {"__interrupt__": (interrupt_value,)})
    evt = chunk_to_event(chunk, thread_id="t-1", trace_id="trace-1")
    assert evt.event == "hitl_requested"
    assert "interrupt_id" in evt.data
    assert evt.data["tool"] == "run_bash"


def test_done_when_no_more_chunks_marker():
    # 内部事件 marker
    chunk = ("__done__", {})
    evt = chunk_to_event(chunk, thread_id="t-1", trace_id="trace-1")
    assert evt.event == "done"


def test_serializes_to_sse_text():
    evt = StreamEvent(event="node_end", thread_id="t-1", data={"k": "v"}, trace_id="trace-1")
    text = format_sse(evt)
    assert text.startswith("event: node_end\n")
    body = text.split("\n\n")[0].split("data: ", 1)[1]
    parsed = json.loads(body)
    assert parsed["thread_id"] == "t-1"
    assert parsed["event"] == "node_end"
    assert parsed["data"]["k"] == "v"
    assert parsed["trace_id"] == "trace-1"


def test_handles_unknown_chunk_gracefully():
    chunk = ("unknown_node_type", {"weird": "shape"})
    evt = chunk_to_event(chunk, thread_id="t-1", trace_id="trace-1")
    # 应该不抛,产生一个 fallback 事件
    assert evt.event in {"node_end", "messages_update"}
