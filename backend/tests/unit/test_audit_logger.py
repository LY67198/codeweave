"""AuditLogger 单元测试(spec §5.2)。"""
from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from codeweave.persistence.audit import AuditLogger, audit_span, audit_tool


@pytest.fixture
def fake_session_factory():
    """返回 (session, factory) 元组;session.add 触发 commit。"""
    session = MagicMock()
    factory = MagicMock(return_value=session)

    ctx = MagicMock()
    ctx.__enter__.return_value = session
    ctx.__exit__.return_value = False
    factory.return_value = ctx
    return session, factory


def test_emit_writes_one_audit_event(fake_session_factory):
    session, factory = fake_session_factory
    logger = AuditLogger(factory)

    logger.emit("tool_call", {"tool": "read_file", "args": {"path": "x"}},
                thread_id="t-1", duration_ms=12)

    session.add.assert_called_once()
    row = session.add.call_args[0][0]
    assert row.thread_id == "t-1"
    assert row.kind == "tool_call"
    assert row.payload == {"tool": "read_file", "args": {"path": "x"}}
    assert row.duration_ms == 12
    session.commit.assert_called_once()


def test_emit_swallows_db_errors_and_does_not_raise(fake_session_factory):
    session, factory = fake_session_factory
    session.commit.side_effect = OperationalError("stmt", {}, Exception("db down"))
    logger = AuditLogger(factory)

    # 不应抛异常
    logger.emit("tool_call", {"x": 1}, thread_id="t-1")


def test_get_thread_timeline_returns_dicts_in_chronological_order(fake_session_factory):
    session, factory = fake_session_factory
    rows = [
        MagicMock(thread_id="t-1", ts=dt.datetime(2026, 7, 8, 10, 0),
                  kind="a", payload={"x": 1}, duration_ms=None),
        MagicMock(thread_id="t-1", ts=dt.datetime(2026, 7, 8, 10, 5),
                  kind="b", payload={"x": 2}, duration_ms=10),
    ]
    scalars = MagicMock()
    scalars.all.return_value = rows
    session.execute.return_value.scalars.return_value = scalars

    logger = AuditLogger(factory)
    timeline = logger.get_thread_timeline("t-1", limit=10)

    assert len(timeline) == 2
    assert timeline[0]["kind"] == "a"
    assert timeline[1]["kind"] == "b"


def test_audit_span_emits_enter_and_exit(fake_session_factory):
    """audit_span 进入时 emit <kind>_enter,退出时 emit <kind>_exit,duration_ms 在 payload 里。"""
    session, factory = fake_session_factory
    logger = AuditLogger(factory)

    with audit_span(logger, "node", thread_id="t-1") as payload:
        payload["marker"] = "ok"

    emitted = [c.args[0] for c in session.add.call_args_list]
    # 两次 add:enter、exit
    kinds = [getattr(e, "kind", None) for e in emitted]
    assert "node_enter" in kinds
    assert "node_exit" in kinds

    exit_row = next(e for e in emitted if getattr(e, "kind", "") == "node_exit")
    assert exit_row.payload.get("marker") == "ok"
    assert isinstance(exit_row.payload.get("duration_ms"), int)
    assert exit_row.payload["duration_ms"] >= 0


def test_audit_tool_records_success_and_duration(fake_session_factory):
    """audit_tool 装饰的工具,在成功调用后 emit tool_call 含 duration_ms。"""
    session, factory = fake_session_factory
    logger = AuditLogger(factory)

    @audit_tool(logger, tool_name_getter=lambda *a, **kw: "read_file")
    def my_tool(path: str, thread_id: str = "<no-thread>") -> str:
        return f"read {path}"

    out = my_tool(path="x.txt", thread_id="t-1")

    assert out == "read x.txt"
    session.add.assert_called_once()
    row = session.add.call_args[0][0]
    assert row.kind == "tool_call"
    assert row.payload["tool"] == "read_file"
    assert row.thread_id == "t-1"
    assert isinstance(row.duration_ms, int)


def test_audit_tool_records_failure_then_reraises(fake_session_factory):
    """audit_tool 工具抛异常时,记录 tool_call 含 error 字段,再 re-raise。"""
    session, factory = fake_session_factory
    logger = AuditLogger(factory)

    @audit_tool(logger, tool_name_getter=lambda *a, **kw: "boom")
    def my_tool(thread_id: str = "<no-thread>") -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        my_tool(thread_id="t-1")

    row = session.add.call_args[0][0]
    assert row.kind == "tool_call"
    assert "error" in row.payload
