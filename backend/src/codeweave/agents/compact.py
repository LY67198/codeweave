"""Compact Agent —— 压缩上下文(占位)。

该 Agent 将在第三阶段实装(对话压缩 / Token 管理)。
当前为占位实现,让 graph 编译通过、supervisor 可路由到 compact。
"""
from codeweave.state.schemas import RootState


def compact_node(state: RootState) -> dict:
    """Compact 节点:压缩消息历史(占位实现)。

    Args:
        state: 当前 graph state。

    Returns:
        包含 ``messages`` 的部分 state 更新,目前为空消息列表。
    """
    return {"messages": []}
