"""Pydantic 模型序列化测试(spec §2.3)。"""
from datetime import datetime

import pytest
from pydantic import ValidationError

from codeweave.api.models.threads import (
    HumanMessageIn,
    ResumeIn,
    StreamEvent,
    ThreadState,
    TimelineResponse,
)


def test_human_message_in_minimal():
    msg = HumanMessageIn(content="hello")
    assert msg.role == "human"
    assert msg.content == "hello"


def test_human_message_in_too_long_raises():
    with pytest.raises(ValidationError):
        HumanMessageIn(content="x" * 32001)


def test_resume_in_requires_decision_dict():
    r = ResumeIn(interrupt_id="i-1", decision={"approve": True})
    assert r.interrupt_id == "i-1"
    assert r.decision == {"approve": True}


def test_stream_event_default_timestamp():
    evt = StreamEvent(
        event="done",
        thread_id="t-1",
        data={},
        trace_id="trace-1",
    )
    assert evt.timestamp.tzinfo is not None  # timezone-aware UTC
    assert evt.event == "done"


def test_thread_state_round_trip():
    state = ThreadState(
        thread_id="t-1",
        messages=[{"role": "human", "content": "hi"}],
        todos=[{"id": "1", "content": "x", "status": "pending", "activeform": "y"}],
        plan_mode=True,
        agent_history=[{"event": "node_enter", "ts": "...", "node": "compact_check"}],
        compact_pending=False,
        last_dispatched_compact_id=None,
    )
    d = state.model_dump(mode="json")
    assert d["thread_id"] == "t-1"
    assert d["messages"][0]["content"] == "hi"


def test_timeline_response_empty():
    r = TimelineResponse(thread_id="t-1", events=[])
    assert r.events == []
