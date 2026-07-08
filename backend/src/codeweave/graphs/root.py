"""Root Graph —— 顶层 StateGraph,组合 Plan 与 Execute 两个 Subgraph。

目前流程为 ``START -> execute -> END``,完整的 plan-mode 中断逻辑
将在第三阶段加入。
"""
from langgraph.graph import END, START, StateGraph

from codeweave.config.settings import get_settings
from codeweave.graphs.execute_graph import build_execute_graph
from codeweave.graphs.plan_graph import build_plan_graph
from codeweave.persistence.checkpointer import get_checkpointer
from codeweave.state.schemas import RootState


def build_root_graph(checkpointer=None):
    """构建顶层 StateGraph,包含 Plan 和 Execute 两个 Subgraph。

    Args:
        checkpointer: 可选的 ``PostgresSaver`` 实例。若为 None,则使用
            ``get_checkpointer()`` 获取默认实例。

    Returns:
        已编译的图,可直接用于 ``invoke`` / ``stream``。
    """
    get_settings()  # 触发 Settings 单例初始化

    plan_subgraph = build_plan_graph().compile()
    execute_subgraph = build_execute_graph().compile()

    builder = StateGraph(RootState)

    # 将 Subgraph 用作节点
    builder.add_node("plan", plan_subgraph)
    builder.add_node("execute", execute_subgraph)

    # 简单流程：plan -> execute -> END
    #（完整的 plan-mode 中断逻辑将在第三阶段加入）
    builder.add_edge(START, "execute")
    builder.add_edge("execute", END)

    # 使用 checkpointer 编译
    cp = checkpointer or get_checkpointer()
    return builder.compile(checkpointer=cp)