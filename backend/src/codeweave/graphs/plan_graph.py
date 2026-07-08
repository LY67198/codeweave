"""Placeholder. Real implementation in next task."""
from langgraph.graph import StateGraph
from codeweave.state.schemas import PlanState


def build_plan_graph() -> StateGraph:
    builder = StateGraph(PlanState)
    return builder