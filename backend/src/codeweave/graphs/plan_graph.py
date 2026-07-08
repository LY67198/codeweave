"""Placeholder. Real implementation in next task."""
from langgraph.graph import END, START, StateGraph
from codeweave.state.schemas import PlanState


def build_plan_graph() -> StateGraph:
    """Placeholder Plan Subgraph (minimal so Root can compile)."""
    builder = StateGraph(PlanState)
    # Minimal stub node so the graph has an entrypoint.
    # Real plan-mode logic added in Phase 3.
    def _passthrough(state):
        return state

    builder.add_node("plan_stub", _passthrough)
    builder.add_edge(START, "plan_stub")
    builder.add_edge("plan_stub", END)
    return builder