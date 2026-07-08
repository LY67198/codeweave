"""compact_check 节点纯逻辑(spec §4.2)。

把核心决策抽到 ``agents/_compact_check.py``,节点函数本身体薄。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from codeweave.agents._compact_check import decide_compact_action


def test_returns_skip_when_interrupt_is_set():
    s = {"messages": [HumanMessage(content="x" * 100)], "__interrupt__": ("hitl",)}
    action = decide_compact_action(
        s,
        threshold=1,
        enabled=True,
        session_factory=MagicMock(),
        dispatch_fn=lambda tid: "x",
        thread_id_getter=lambda st: "thread-1",
    )
    assert action.kind == "skip"


def test_returns_skip_when_disabled():
    s = {"messages": [HumanMessage(content="x" * 1000)]}
    action = decide_compact_action(
        s,
        threshold=1,
        enabled=False,
        session_factory=MagicMock(),
        dispatch_fn=lambda tid: "x",
        thread_id_getter=lambda st: "thread-1",
    )
    assert action.kind == "skip"


def test_returns_direct_executor_when_under_threshold():
    s = {"messages": [HumanMessage(content="hi")]}
    action = decide_compact_action(
        s,
        threshold=100_000,
        enabled=True,
        session_factory=MagicMock(),
        dispatch_fn=lambda tid: "x",
        thread_id_getter=lambda st: "thread-1",
    )
    assert action.kind == "executor"


def test_returns_dispatch_when_over_threshold_and_no_pending():
    s = {"messages": [HumanMessage(content="x" * 10_000)]}
    factory = MagicMock()
    session = MagicMock()
    factory.return_value.__enter__.return_value = session
    # 两次查询(done 优先,然后 pending)都返回 None → 走到 insert + dispatch 路径
    session.execute.return_value.scalar_one_or_none.return_value = None
    # insert 流程
    session.add.return_value = None

    action = decide_compact_action(
        s,
        threshold=1,
        enabled=True,
        session_factory=factory,
        dispatch_fn=lambda tid: "compact-id-1",
        thread_id_getter=lambda st: "thread-1",
    )

    assert action.kind == "dispatch"
    assert action.compact_pending is True
    assert action.compact_id == "compact-id-1"


def test_returns_wait_when_pending_row_exists():
    s = {"messages": [HumanMessage(content="x" * 10_000)]}
    factory = MagicMock()
    session = MagicMock()
    factory.return_value.__enter__.return_value = session
    # done 优先查询返回 None,pending 查询返回已有行
    pending = MagicMock(id="already-pending", status="pending", applied=False)

    # 用于支持 execute.side_effect 顺序模拟两次查询
    done_result = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    pending_result = MagicMock(scalar_one_or_none=MagicMock(return_value=pending))
    session.execute.side_effect = [done_result, pending_result]

    action = decide_compact_action(
        s,
        threshold=1,
        enabled=True,
        session_factory=factory,
        dispatch_fn=lambda tid: "compact-id-NEW",
        thread_id_getter=lambda st: "thread-1",
    )

    assert action.kind == "__end__"
    # 没调 dispatch_fn
    # (compact_id 可以是已经存在的行 id 或 None;这里定义为 None 表示本次未分派新 id)


def test_returns_apply_when_done_row_exists():
    s = {"messages": [HumanMessage(content="x" * 10_000)]}
    factory = MagicMock()
    session = MagicMock()
    factory.return_value.__enter__.return_value = session
    done = MagicMock(
        id="done-1",
        status="done",
        applied=False,
        summary_message={"role": "system", "content": "SUMMARY"},
        keep_first=0,
        keep_last=1,
    )
    # done 查询命中
    done_result = MagicMock(scalar_one_or_none=MagicMock(return_value=done))
    session.execute.return_value = done_result

    action = decide_compact_action(
        s,
        threshold=1,
        enabled=True,
        session_factory=factory,
        dispatch_fn=lambda tid: "x",
        thread_id_getter=lambda st: "thread-1",
    )

    assert action.kind == "executor"
    assert action.new_messages is not None
    assert any("SUMMARY" in m.content for m in action.new_messages)  # type: ignore[union-attr]
