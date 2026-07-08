from langgraph.graph import END, START, StateGraph

from codeweave.agents import (
    coder_node, executor_node, explorer_node, reviewer_node, supervisor_node,
)
from codeweave.state.schemas import ExecuteState


def build_execute_graph() -> StateGraph:
    """构建 Execute Subgraph（读+写阶段）。"""
    builder = StateGraph(ExecuteState)

    # 添加节点
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("explorer", explorer_node)
    builder.add_node("coder", coder_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("executor", executor_node)

    # 入口：从父图进入 supervisor
    builder.add_edge(START, "supervisor")

    # 来自 supervisor 的条件路由
    # supervisor_node 返回的 Command.goto 已经直接处理路由
    # 但对于直接返回 dict 的节点也需要回退边
    builder.add_edge("explorer", "supervisor")
    builder.add_edge("executor", "supervisor")

    return builder