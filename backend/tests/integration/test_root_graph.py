import os
import pytest
from codeweave.graphs.root import build_root_graph


@pytest.fixture(autouse=True)
def require_postgres():
    """若没有可用的 postgres 则跳过。"""
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url:
        pytest.skip("DATABASE_URL not set")


def test_root_graph_compiles_with_checkpointer():
    g = build_root_graph()
    assert g is not None