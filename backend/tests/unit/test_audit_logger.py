"""AuditLogger 单元测试(spec §5.2)。"""
from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from codeweave.persistence.audit import AuditLogger


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
