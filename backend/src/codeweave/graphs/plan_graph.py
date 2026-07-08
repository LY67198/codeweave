"""Plan Subgraph —— 计划阶段(占位实现)。

完整的 plan-mode 逻辑将在第三阶段加入。
"""
from langgraph.graph import END, START, StateGraph
from codeweave.state.schemas import PlanState


def build_plan_graph() -> StateGraph:
    """占位的 Plan Subgraph(最小实现以保证 Root 可以编译)。

    Returns:
        未编译的 ``StateGraph`` 构建器实例,内含一个透传的 ``plan_stub`` 节点。
    """
    builder = StateGraph(PlanState)
    # 添加最小的桩节点以提供图入口。
    # 完整的 plan-mode 逻辑将在第三阶段加入。
    def _passthrough(state):
        return state

    builder.add_node("plan_stub", _passthrough)
    builder.add_edge(START, "plan_stub")
    builder.add_edge("plan_stub", END)
    return builder