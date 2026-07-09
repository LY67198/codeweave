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


# 以下覆盖 LangGraph 实际产出 shape — Task 8 验证后补(LangGraph stream_mode="updates"
# 真产出 dict shape,Task 4 / Task 7 旧 tuple shape 测试被保留作 compat)


def test_dict_shape_node_end_chunk():
    """LangGraph 真产出:``{"node_name": state_update_dict}`` 的 dict。"""
    chunk = {"executor": {"_agent_history": ["h1"], "todos": []}}
    evt = chunk_to_event(chunk, thread_id="t-1", trace_id="trace-1")
    assert evt.event == "node_end"
    assert evt.node == "executor"
    assert evt.data["_agent_history"] == ["h1"]


def test_dict_shape_messages_update():
    chunk = {"executor": {"messages": [HumanMessage_spec := "hello"]}}
    # 用 MagicMock 形式避免 import BaseMessage
    import sys
    from unittest.mock import MagicMock
    bm = MagicMock()
    bm.type = "human"
    bm.content = "hello"
    chunk = {"executor": {"messages": [bm]}}
    evt = chunk_to_event(chunk, thread_id="t-1", trace_id="trace-1")
    assert evt.event == "messages_update"
    assert "messages" in evt.data


def test_dict_shape_interrupt():
    """LangGraph 真产出:``{"__interrupt__": (Interrupt(...),)}`` 的 dict。"""
    interrupt_value = Interrupt(value={"prompt": "approve?", "tool": "run_bash", "command": "rm /"})
    chunk = {"__interrupt__": (interrupt_value,)}
    evt = chunk_to_event(chunk, thread_id="t-1", trace_id="trace-1")
    assert evt.event == "hitl_requested"
    assert "interrupt_id" in evt.data
    assert evt.data["tool"] == "run_bash"


def test_dict_shape_empty_fallback():
    chunk = {"__metadata__": ["internal"]}
    evt = chunk_to_event(chunk, thread_id="t-1", trace_id="trace-1")
    assert evt.event == "node_end"
    assert "raw" in evt.data


def test_dict_shape_coder_diff_emits_coder_diff_event():
    """coder 节点产出 coder_diff → 映射 coder_diff event。"""
    chunk = {"coder": {"coder_diff": "--- x.py\n+new\n"}}
    evt = chunk_to_event(chunk, thread_id="t", trace_id="tr")
    assert evt.event == "coder_diff"
    assert evt.node == "coder"
    assert "x.py" in evt.data.get("coder_diff", "")


def test_dict_shape_reviewer_decision_emits_reviewer_decision_event():
    """reviewer 节点产出 reviewer_decision → 映射 reviewer_decision event。"""
    chunk = {"reviewer": {"reviewer_decision": {"accept": True, "score": 8, "feedback": "ok", "risk_flags": []}}}
    evt = chunk_to_event(chunk, thread_id="t", trace_id="tr")
    assert evt.event == "reviewer_decision"
    assert evt.node == "reviewer"
    assert evt.data["reviewer_decision"]["accept"] is True


def test_dict_shape_retry_count_increment_emits_coder_retry():
    """coder retry 时 retry_count 自增 → 映射 coder_retry event。"""
    chunk = {"coder": {"coder_diff": "--- x", "retry_count": 2}}
    evt = chunk_to_event(chunk, thread_id="t", trace_id="tr")
    assert evt.event == "coder_retry"
    assert evt.data.get("retry_count") == 2


def test_dict_shape_no_special_keys_falls_to_node_end():
    """无特殊字段 → 普通 node_end(向后兼容)。"""
    chunk = {"executor": {"_agent_history": ["x"]}}
    evt = chunk_to_event(chunk, thread_id="t", trace_id="tr")
    assert evt.event == "node_end"
    assert evt.node == "executor"
