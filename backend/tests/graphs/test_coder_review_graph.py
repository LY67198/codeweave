"""coder_review_subgraph 接线测试(spec §4)。"""
from typing import Any
from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import AIMessage

from codeweave.graphs.coder_review_graph import (
    build_coder_review_graph,
    finalize_node,
    _route_after_reviewer,
)


def _build_graph_with_mocks(llm_responses: list[Any]):
    """在 patch 上下文里返回 (compiled_graph, llm_mock, ExitStack)。

    调用方负责 ``with _build_graph_with_mocks(...)[2]:`` 或直接用返回的 stack
    管理生命周期,使 ``g.invoke(...)`` 仍在 mock 上下文内执行。
    """
    from contextlib import ExitStack

    llm = MagicMock()
    # Coder 通过 ``llm.bind_tools(...).invoke(...)`` 调,Reviewer 直接 ``llm.invoke(...)``
    # — 两边的 invoke 都需要从 side_effect 顺序取值。
    iter_responses = iter(llm_responses)

    def bind_tools_then_invoke(*_args, **_kwargs):
        return MagicMock(invoke=lambda *_a, **_k: next(iter_responses))

    llm.bind_tools.side_effect = bind_tools_then_invoke
    llm.invoke.side_effect = lambda *_a, **_k: next(iter_responses)

    stack = ExitStack()
    stack.enter_context(patch("codeweave.agents.coder.get_chat_model", return_value=llm))
    stack.enter_context(patch("codeweave.agents.coder.run_tools_and_diff",
                              return_value=([], "--- x.py\n+new\n", {"x.py": True})))
    stack.enter_context(patch("codeweave.agents.coder.load_skills_for", return_value=[]))
    stack.enter_context(patch("codeweave.agents.reviewer.load_skills_for", return_value=[]))
    stack.enter_context(patch("codeweave.agents.reviewer.get_chat_model", return_value=llm))
    stack.enter_context(patch("codeweave.config.model.get_chat_model", return_value=llm))
    g = build_coder_review_graph().compile(checkpointer=InMemorySaver())
    return g, llm, stack


def _compile_with_mocked_llm(llm_responses: list[Any]):
    """每次 invoke 返回列表里的下一个 response。

    保留向后兼容:返回 ``(g, llm)`` 但需要调用方用 stack 维持 patch。
    """
    g, llm, _ = _build_graph_with_mocks(llm_responses)
    return g, llm


# _route_after_reviewer
def test_route_accept_goes_to_finalize():
    state = {"reviewer_decision": {"accept": True}, "retry_count": 1}
    assert _route_after_reviewer(state) == "finalize"


def test_route_reject_under_limit_loops():
    state = {"reviewer_decision": {"accept": False}, "retry_count": 1}
    assert _route_after_reviewer(state) == "coder"


def test_route_max_retries_goes_to_finalize():
    state = {"reviewer_decision": {"accept": False}, "retry_count": 3}
    assert _route_after_reviewer(state) == "finalize"


# finalize_node
def test_finalize_approved_when_accept():
    out = finalize_node({
        "coder_diff": "--- x.py",
        "reviewer_decision": {"accept": True},
    })
    assert out["final_status"] == "approved"
    assert out["approved_diff"] == "--- x.py"


def test_finalize_max_retries_when_reject():
    out = finalize_node({
        "coder_diff": "--- x.py",
        "reviewer_decision": {"accept": False, "feedback": "bad"},
    })
    assert out["final_status"] == "max_retries_exceeded"
    assert out["approved_diff"] is None
    assert out["last_feedback"] == "bad"


# End-to-end via subgraph
def test_subgraph_approve_on_first_try():
    accept_json = '{"accept": true, "score": 9, "feedback": "lgtm", "risk_flags": []}'
    g, _, stack = _build_graph_with_mocks([
        AIMessage(content="", tool_calls=[{"id": "1", "name": "noop", "args": {}}]),
        type("F", (), {"content": accept_json})(),  # reviewer response
    ])
    with stack:
        out = g.invoke(
            {"request": "x", "thread_id": "t1"},
            config={"configurable": {"thread_id": "t1"}},
        )
    assert out["final_status"] == "approved"
    assert out["approved_diff"]


def test_subgraph_max_retries():
    """3 次 reject,verify final_status = max_retries_exceeded"""
    reject_json = '{"accept": false, "score": 2, "feedback": "no", "risk_flags": []}'
    g, _, stack = _build_graph_with_mocks([
        AIMessage(content="", tool_calls=[]),
        type("F", (), {"content": reject_json})(),  # 1st reviewer reject
        AIMessage(content="", tool_calls=[]),
        type("F", (), {"content": reject_json})(),  # 2nd
        AIMessage(content="", tool_calls=[]),
        type("F", (), {"content": reject_json})(),  # 3rd → finalize
    ])
    with stack:
        out = g.invoke(
            {"request": "x", "thread_id": "t-retry"},
            config={"configurable": {"thread_id": "t-retry"}},
        )
    assert out["final_status"] == "max_retries_exceeded"
    assert out["approved_diff"] is None


def test_subgraph_accept_on_third_retry():
    """1st reject → 2nd reject → 3rd accept → approved."""
    responses = [
        AIMessage(content="", tool_calls=[]),
        type("F1", (), {"content": '{"accept": false, "score": 2, "feedback": "x", "risk_flags": []}'})(),
        AIMessage(content="", tool_calls=[]),
        type("F2", (), {"content": '{"accept": false, "score": 4, "feedback": "y", "risk_flags": []}'})(),
        AIMessage(content="", tool_calls=[]),
        type("F3", (), {"content": '{"accept": true, "score": 9, "feedback": "lgtm", "risk_flags": []}'})(),
    ]
    g, _, stack = _build_graph_with_mocks(responses)
    with stack:
        out = g.invoke(
            {"request": "x", "thread_id": "t-third"},
            config={"configurable": {"thread_id": "t-third"}},
        )
    assert out["final_status"] == "approved"
