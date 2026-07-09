"""coder_review_subgraph:Coder(Produce) ↔ Reviewer(Judge) 循环(spec §4)。"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from codeweave.agents.coder import coder_node
from codeweave.agents.reviewer import reviewer_node
from codeweave.config.settings import get_settings
from codeweave.skills.state import CodeModState


def _route_after_reviewer(state: CodeModState) -> str:
    """Phase 5 route:accept | max_retries → finalize;else → coder。"""
    d: dict[str, Any] = state.get("reviewer_decision", {}) or {}
    if d.get("accept"):
        return "finalize"
    max_retries = get_settings().code_mod_max_retries
    if state.get("retry_count", 0) >= max_retries:
        return "finalize"
    return "coder"


def finalize_node(state: CodeModState) -> dict[str, Any]:
    """收尾:产 final_status + approved_diff / last_feedback。"""
    d: dict[str, Any] = state.get("reviewer_decision", {}) or {}
    if d.get("accept"):
        return {
            "approved_diff": state.get("coder_diff"),
            "final_status": "approved",
        }
    return {
        "approved_diff": None,
        "final_status": "max_retries_exceeded",
        "last_feedback": d.get("feedback", ""),
    }


def build_coder_review_graph() -> StateGraph[CodeModState]:
    """Build subgraph spec §4.1。

    入口:coder → reviewer → (if accept or max) finalize → END
                                ↘ else → coder
    """
    g: StateGraph[CodeModState] = StateGraph(CodeModState)
    g.add_node("coder", coder_node)
    g.add_node("reviewer", reviewer_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "coder")
    g.add_edge("coder", "reviewer")
    g.add_conditional_edges(
        "reviewer",
        _route_after_reviewer,
        {"finalize": "finalize", "coder": "coder"},
    )
    g.add_edge("finalize", END)
    return g


__all__ = ["build_coder_review_graph", "finalize_node", "_route_after_reviewer"]
