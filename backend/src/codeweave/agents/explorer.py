"""Explorer Agent —— 只读探索代码库。

该 Agent 在第二阶段将被替换为基于工具的实际实现。
"""
from codeweave.state.schemas import RootState


def explorer_node(state: RootState) -> dict:
    """Explorer 节点:只读地探索代码库结构(占位实现)。

    Args:
        state: 当前 graph state。

    Returns:
        包含 ``messages`` 的部分 state 更新,目前为空消息列表。
    """
    return {"messages": []}