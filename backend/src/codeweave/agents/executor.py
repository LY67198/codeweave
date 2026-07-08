"""Executor Agent —— 执行测试或构建命令并收集结果。

该 Agent 在第二阶段将被替换为基于工具的实际实现。
"""
from codeweave.state.schemas import RootState


def executor_node(state: RootState) -> dict:
    """Executor 节点:运行测试/构建等命令并收集结果(占位实现)。

    Args:
        state: 当前 graph state。

    Returns:
        包含 ``messages`` 的部分 state 更新,目前为空消息列表。
    """
    return {"messages": []}