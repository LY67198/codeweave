from langgraph.graph import END, START, StateGraph

from codeweave.config.settings import get_settings
from codeweave.graphs.execute_graph import build_execute_graph
from codeweave.graphs.plan_graph import build_plan_graph
from codeweave.persistence.checkpointer import get_checkpointer
from codeweave.state.schemas import RootState


def build_root_graph(checkpointer=None):
    """Build the top-level StateGraph with Plan + Execute Subgraphs.

    Args:
        checkpointer: Optional PostgresSaver instance. If None, uses default.

    Returns:
        Compiled graph ready for invoke/stream.
    """
    settings = get_settings()

    plan_subgraph = build_plan_graph().compile()
    execute_subgraph = build_execute_graph().compile()

    builder = StateGraph(RootState)

    # Use subgraphs as nodes
    builder.add_node("plan", plan_subgraph)
    builder.add_node("execute", execute_subgraph)

    # Simple flow: plan → execute → END
    # (Real plan-mode interrupt logic added in Phase 3)
    builder.add_edge(START, "execute")
    builder.add_edge("execute", END)

    # Compile with checkpointer
    cp = checkpointer or get_checkpointer()
    return builder.compile(checkpointer=cp)