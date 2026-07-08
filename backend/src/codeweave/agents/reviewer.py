"""Reviewer Agent —— 审查 Coder 提交的代码变更。

该 Agent 在第二阶段将被替换为基于工具的实际实现。
"""
from codeweave.state.schemas import RootState


def reviewer_node(state: RootState) -> dict:
    """Reviewer 节点:审查 Coder 产生的 diff 并给出反馈(占位实现)。

    Args:
        state: 当前 graph state。

    Returns:
        包含 ``messages`` 的部分 state 更新,目前为空消息列表。
    """
    return {"messages": []}