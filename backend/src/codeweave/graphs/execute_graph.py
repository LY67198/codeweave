"""Execute Subgraph —— 协调 Supervisor 与各个执行 Agent。

该子图负责在 ``START -> supervisor`` 之后,根据 ``supervisor_node`` 的
``Command.goto`` 路由到具体的 explorer/coder/reviewer/executor。
"""
from langgraph.graph import END, START, StateGraph

from codeweave.agents import (
    coder_node, executor_node, explorer_node, reviewer_node, supervisor_node,
)
from codeweave.agents.executor import _get_executor_tool_node
from codeweave.state.schemas import ExecuteState


def build_execute_graph() -> StateGraph:
    """构建 Execute Subgraph(读+写阶段)。

    节点与边:
        - ``START -> supervisor``: 每次进入子图都先经过 Supervisor 决策。
        - ``supervisor -> *``: 由 ``supervisor_node`` 返回的 ``Command.goto`` 处理。
        - ``explorer -> supervisor`` 与 ``executor -> supervisor``: 兜底回退边,
          用于直接返回 dict 的节点回到 Supervisor 重新决策。

    Returns:
        未编译的 ``StateGraph`` 构建器实例,调用方负责 ``.compile()``。
    """
    builder = StateGraph(ExecuteState)

    # 添加节点
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("explorer", explorer_node)
    builder.add_node("coder", coder_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("executor", executor_node)
    # ToolNode:执行 executor 产生的 tool_call
    builder.add_node("tools", _get_executor_tool_node())

    # 入口：从父图进入 supervisor
    builder.add_edge(START, "supervisor")

    # 来自 supervisor 的条件路由
    # supervisor_node 返回的 Command.goto 已经直接处理路由
    # 但对于直接返回 dict 的节点也需要回退边
    builder.add_edge("explorer", "supervisor")
    builder.add_edge("executor", "supervisor")

    return builder