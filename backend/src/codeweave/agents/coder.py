"""Coder Agent —— 编写和修改代码。

该 Agent 在第二阶段将被替换为基于工具的实际实现。
"""
from codeweave.state.schemas import RootState


def coder_node(state: RootState) -> dict:
    """Coder 节点:读取任务上下文并产出代码变更(占位实现)。

    Args:
        state: 当前 graph state。

    Returns:
        包含 ``messages`` 的部分 state 更新,目前为空消息列表。
    """
    return {"messages": []}