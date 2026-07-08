"""execute_graph 拓扑测试(spec §4.6)。

确认:
- ``__start__`` → ``compact_check`` 是首条边
- ``compact_check → executor``(under-threshold path)
- ``compact_check → __end__``(dispatch / wait path)
"""
from __future__ import annotations

from langgraph.constants import END
from langgraph.graph import START

from codeweave.graphs.execute_graph import build_execute_graph


def _entry_destinations(graph) -> set[str]:
    """从 ``graph.edges`` 提取 ``__start__`` 出边的目标集合。

    Args:
        graph: ``StateGraph`` 构建器实例。

    Returns:
        从 ``__start__`` 出发到达的所有节点名集合。
    """
    return {tgt for src, tgt in graph.edges if src == START}


def _conditional_destinations(graph, source: str) -> set[str]:
    """提取 ``source`` 节点的条件边可达目的地集合。

    遍历 ``graph.branches[source]`` 中的所有 ``BranchSpec``,取其
    ``ends`` dict 的值并集(同源节点可能挂多个条件分支)。

    Args:
        graph: ``StateGraph`` 构建器实例。
        source: 源节点名。

    Returns:
        条件边可路由到的所有目的地节点名集合。
    """
    destinations: set[str] = set()
    for spec in graph.branches[source].values():
        destinations.update(spec.ends.values())
    return destinations


def test_compact_check_is_entry_node():
    """compact_check 必须是 execute_graph 的入口节点。"""
    graph = build_execute_graph()
    assert "compact_check" in graph.nodes
    entry_dests = _entry_destinations(graph)
    assert entry_dests == {"compact_check"}


def test_compact_check_conditional_routes_to_executor_and_end():
    """compact_check 条件边必须能路由到 executor 与 __end__。"""
    graph = build_execute_graph()
    assert "compact_check" in graph.branches
    destinations = _conditional_destinations(graph, "compact_check")
    assert {"executor", END} <= destinations


def test_existing_topology_preserved():
    """已有拓扑(executor ⇄ tools、explorer 回 supervisor 兜底边)必须保留。"""
    graph = build_execute_graph()
    # ReAct 双节点必须仍存在
    assert {"supervisor", "explorer", "coder", "reviewer",
            "executor", "tools", "compact_check"}.issubset(set(graph.nodes))
    # tools → executor 普通边必须保留(ReAct 自循环)
    assert ("tools", "executor") in graph.edges
    # explorer → supervisor 兜底边必须保留
    assert ("explorer", "supervisor") in graph.edges


def test_execute_graph_with_compact_check_compiles():
    """加入 compact_check 入口后图仍能成功编译。"""
    graph = build_execute_graph()
    compiled = graph.compile()
    assert compiled is not None
