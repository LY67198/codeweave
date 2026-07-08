from langgraph.graph import END, START, StateGraph

from codeweave.agents import (
    coder_node, executor_node, explorer_node, reviewer_node, supervisor_node,
)
from codeweave.state.schemas import ExecuteState


def build_execute_graph() -> StateGraph:
    """Build the Execute Subgraph (read+write phase)."""
    builder = StateGraph(ExecuteState)

    # Add nodes
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("explorer", explorer_node)
    builder.add_node("coder", coder_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("executor", executor_node)

    # Entry: from parent graph into supervisor
    builder.add_edge(START, "supervisor")

    # Conditional routing from supervisor
    # The Command.goto returned by supervisor_node handles routing directly
    # But we also need fallback edges for nodes that return plain dicts
    builder.add_edge("explorer", "supervisor")
    builder.add_edge("executor", "supervisor")

    return builder