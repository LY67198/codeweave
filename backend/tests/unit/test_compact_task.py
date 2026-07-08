"""compact_thread Celery task 单元测试(spec §4.3)。

注意:本测试不连真实 PostgreSQL,通过 MagicMock 替换
``codeweave.tasks.compact`` 内的 ``_get_checkpointer`` 与 ``SessionLocal``,
仅验证任务逻辑分支(read state → LLM summarize → write row → status)。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from codeweave.db.models import CompactResult
from codeweave.tasks.compact import compact_thread


def _make_session_ctx(monkeypatch, row: CompactResult | None) -> MagicMock:
    """构造 SessionLocal 上下文管理器 mock。

    Args:
        monkeypatch: pytest 内置 fixture。
        row: 已经存在的 pending ``CompactResult``(None 表示库里没有)。

    Returns:
        已 patch 进 ``codeweave.tasks.compact.SessionLocal`` 的 mock。
    """
    session = MagicMock()
    # session.execute(...).scalar_one_or_none() 返回 row
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = row
    session.execute.return_value = scalar_result

    ctx = MagicMock()
    ctx.__enter__.return_value = session
    ctx.__exit__.return_value = False
    monkeypatch.setattr("codeweave.tasks.compact.SessionLocal", lambda: ctx)
    return session


def _stub_audit(monkeypatch) -> MagicMock:
    """静默 audit emit,避免依赖 DB。"""
    stub = MagicMock()
    monkeypatch.setattr("codeweave.tasks.compact._audit", stub)
    return stub


def _stub_tracker(monkeypatch) -> MagicMock:
    """静默 token_tracker.track。"""
    stub = MagicMock()
    monkeypatch.setattr("codeweave.tasks.compact._tracker", stub)
    return stub


def test_compact_thread_writes_status_done_when_reduction(
    monkeypatch, fake_checkpointer
):
    """长消息 → LLM 摘要后 → tokens_after < tokens_before → row.status='done'。"""
    # 30 条 HumanMessage,每条 50 token,首条系统消息保留,后 6 条保留
    sys_msg = SystemMessage(content="sys")
    long_msgs = [sys_msg] + [HumanMessage(content="x " * 100) for _ in range(99)]
    fake_checkpointer.get_tuple.return_value.checkpoint = {"channel_values": {"messages": long_msgs}}

    _stub_audit(monkeypatch)
    tracker_stub = _stub_tracker(monkeypatch)

    thread_id = "t-c1"
    pending_row = CompactResult(
        thread_id=thread_id, status="pending", applied=False
    )
    pending_row.id = "11111111-1111-1111-1111-111111111111"  # type: ignore[assignment]
    session = _make_session_ctx(monkeypatch, pending_row)

    with patch(
        "codeweave.tasks.compact.llm_summarize",
        return_value=("简洁摘要", 5),  # 短摘要 → tokens_after 必然更小
    ):
        result_id = compact_thread.apply(args=[thread_id]).get()

    # 写到 row 的字段被设置
    assert pending_row.summary_message == {
        "role": "system",
        "content": "简洁摘要",
    }
    assert pending_row.status == "done"
    assert pending_row.error is None
    assert result_id == str(pending_row.id)
    session.commit.assert_called_once()
    tracker_stub.track.assert_called_once()


def test_compact_thread_marks_no_reduction(
    monkeypatch, fake_checkpointer
):
    """LLM 返回摘要比原文还长 → row.status='failed',error='no_reduction'。"""
    sys_msg = SystemMessage(content="sys")
    # 5 条短消息,即使 keep_last=6 也基本无可压缩区间
    msgs = [sys_msg, HumanMessage(content="hi"), HumanMessage(content="ho")]
    fake_checkpointer.get_tuple.return_value.checkpoint = {"channel_values": {"messages": msgs}}

    _stub_audit(monkeypatch)
    _stub_tracker(monkeypatch)

    thread_id = "t-c2"
    pending_row = CompactResult(
        thread_id=thread_id, status="pending", applied=False
    )
    pending_row.id = "22222222-2222-2222-2222-222222222222"  # type: ignore[assignment]
    _make_session_ctx(monkeypatch, pending_row)

    # 故意让 summary 比原文本还大
    huge_summary = "y " * 10_000
    with patch(
        "codeweave.tasks.compact.llm_summarize",
        return_value=(huge_summary, len(huge_summary)),
    ):
        # msgs 太短,keep_first == keep_last == len(messages),应直接返回空串
        result_id = compact_thread.apply(args=[thread_id]).get()

    # 消息太短 → nothing_to_compact,空串返回
    assert result_id == ""


def test_compact_thread_creates_row_when_no_pending(
    monkeypatch, fake_checkpointer
):
    """库里没有 pending row → 任务自己 INSERT 一条新的并设 status。"""
    sys_msg = SystemMessage(content="sys")
    long_msgs = [sys_msg] + [HumanMessage(content="x " * 100) for _ in range(50)]
    fake_checkpointer.get_tuple.return_value.checkpoint = {"channel_values": {"messages": long_msgs}}

    _stub_audit(monkeypatch)
    _stub_tracker(monkeypatch)

    # session.execute(...).scalar_one_or_none() → None(无 pending)
    session = _make_session_ctx(monkeypatch, None)

    # 创建一个会被 session.add 后取到的 row;通过 side_effect 给 add 注入 row.id
    new_row = CompactResult(thread_id="t-c3", status="pending", applied=False)
    new_row.id = "33333333-3333-3333-3333-333333333333"  # type: ignore[assignment]

    def _add_side_effect(obj):
        # 把新建 row 的 id 填上,模拟 server_default gen_random_uuid()
        obj.id = new_row.id  # type: ignore[attr-defined]

    session.add.side_effect = _add_side_effect

    with patch(
        "codeweave.tasks.compact.llm_summarize",
        return_value=("短摘要", 4),
    ):
        result_id = compact_thread.apply(args=["t-c3"]).get()

    session.add.assert_called()
    session.flush.assert_called_once()
    session.commit.assert_called_once()
    assert result_id == str(new_row.id)


def test_compact_thread_retries_on_llm_failure(
    monkeypatch, fake_checkpointer
):
    """LLM 抛异常 → self.retry 被调用一次,audit emit compact_failed。"""
    sys_msg = SystemMessage(content="sys")
    long_msgs = [sys_msg] + [HumanMessage(content="x " * 100) for _ in range(50)]
    fake_checkpointer.get_tuple.return_value.checkpoint = {"channel_values": {"messages": long_msgs}}

    audit_stub = _stub_audit(monkeypatch)
    _stub_tracker(monkeypatch)

    # LLM 抛异常 → self.retry 被调用
    with patch(
        "codeweave.tasks.compact.llm_summarize",
        side_effect=RuntimeError("boom"),
    ):
        # eager 模式下,retry 仍会触发 MaxRetriesExceededError
        with pytest.raises(Exception):
            compact_thread.apply(args=["t-c4"]).get()

    # audit 至少 emit 了一次 compact_failed
    kinds = [c.args[0] for c in audit_stub.emit.call_args_list]
    assert "compact_failed" in kinds