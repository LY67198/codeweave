"""占位文件。完整实现将在下一个任务中完成。"""
from langgraph.graph import END, START, StateGraph
from codeweave.state.schemas import PlanState


def build_plan_graph() -> StateGraph:
    """占位的 Plan Subgraph（最小实现以保证 Root 可以编译）。"""
    builder = StateGraph(PlanState)
    # 添加最小的桩节点以提供图入口。
    # 完整的 plan-mode 逻辑将在第三阶段加入。
    def _passthrough(state):
        return state

    builder.add_node("plan_stub", _passthrough)
    builder.add_edge(START, "plan_stub")
    builder.add_edge("plan_stub", END)
    return builder