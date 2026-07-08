from codeweave.graphs.execute_graph import build_execute_graph


def test_build_execute_graph_has_all_nodes():
    g = build_execute_graph()
    nodes = g.nodes
    expected = {"supervisor", "explorer", "coder", "reviewer", "executor"}
    assert expected.issubset(set(nodes.keys()))


def test_execute_graph_compiles():
    g = build_execute_graph()
    compiled = g.compile()
    assert compiled is not None