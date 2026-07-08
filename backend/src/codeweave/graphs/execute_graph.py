"""Execute Subgraph —— 协调 Supervisor 与各个执行 Agent。

该子图负责在 ``START -> compact_check`` 之后,根据 ``compact_check_node``
的决策路由到 Supervisor 或直接结束。再由 ``supervisor_node`` 的
``Command.goto`` 路由到具体的 explorer/coder/reviewer/executor。
Executor 与 tools 节点形成标准 ReAct 循环(Reasoning ⇄ Acting)。
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from codeweave.agents import (
    coder_node, compact_node, executor_node, explorer_node, reviewer_node,
    supervisor_node,
)
from codeweave.agents.compact import compact_check_node
from codeweave.agents.executor import executor_tools_node
from codeweave.state.schemas import ExecuteState


def _route_after_compact_check(state: dict[str, Any]) -> str:
    """``compact_check_node`` 之后的条件路由函数。

    优先读取 state 中的 ``next_agent`` 字段(由 ``compact_check_node``
    在 dispatch / wait 路径下显式设置);默认走 ``executor``,即
    skip / under-threshold / apply 等"正常流转"路径。

    Args:
        state: LangGraph 当前 state 字典。

    Returns:
        下一跳节点名:``"executor"`` 或 ``"__end__"``。
    """
    next_agent: Any = state.get("next_agent") if hasattr(state, "get") else None
    if next_agent in {"executor", "__end__"}:
        return str(next_agent)
    return "executor"


def build_execute_graph() -> StateGraph:  # type: ignore[type-arg]
    """构建 Execute Subgraph(读+写阶段)。

    节点与边:
        - ``START -> compact_check``: 每次进入子图先做 compact 决策。
          ``compact_check_node`` 通过返回 state 中的 ``next_agent`` 决定下一步
          走向 ``executor``(正常流转)或直接 ``__end__``(dispatch / wait 路径)。
          ``executor`` 处的 ``Command.goto`` 进一步决定回到 ``supervisor`` 还是
          终止。
        - ``compact_check -> __end__``: dispatch 已派发或 wait 等下一 turn 的
          路径,本 turn 不再流到 supervisor。
        - ``supervisor -> *``: 由 ``supervisor_node`` 返回的 ``Command.goto``
          处理。
        - ``executor ⇄ tools``: 标准 ReAct 双节点。
          executor 调 LLM,若返回 tool_calls 则 ``Command(goto="tools")``;
          tools 跑 ToolNode,执行完 ``Command(goto="executor")`` 继续 Reasoning。
          直至 LLM 不再调工具 → ``Command(goto="__end__")`` 结束。
        - ``explorer -> supervisor``: 兜底回退边,
          用于直接返回 dict 的节点回到 Supervisor 重新决策。

    Returns:
        未编译的 ``StateGraph`` 构建器实例,调用方负责 ``.compile()``。
    """
    builder = StateGraph(ExecuteState)

    # 添加节点
    builder.add_node("compact_check", compact_check_node)  # Phase 3 实装入口
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("explorer", explorer_node)
    builder.add_node("coder", coder_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("compact", compact_node)  # 占位保留(向后兼容)
    # ReAct 双节点
    builder.add_node("executor", executor_node)
    builder.add_node("tools", executor_tools_node)

    # 入口:从父图进入 compact_check
    builder.add_edge(START, "compact_check")
    # compact_check 条件路由:基于 next_agent 决定流向 supervisor 链或 __end__
    builder.add_conditional_edges(
        "compact_check",
        _route_after_compact_check,
        {
            "executor": "executor",
            "__end__": "__end__",
        },
    )

    # ReAct 循环的拓扑边(实际路由由 Command.goto 决定,这里只是声明图结构)
    # 注意:不要添加 ``executor -> supervisor`` 静态边(ReAct 自循环)
    builder.add_edge("tools", "executor")
    builder.add_edge("executor", END)  # 兜底:executor.goto="__end__" 时也能退出

    # 来自 supervisor 的条件路由
    # supervisor_node 返回的 Command.goto 已经直接处理路由
    # 但对于直接返回 dict 的节点也需要回退边
    builder.add_edge("explorer", "supervisor")

    return builder
