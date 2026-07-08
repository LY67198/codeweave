"""Store 层单元测试(spec §5.1)。

Phase 3 不引入真正 PostgresStore(版本不确定,见 §10 Open Questions 1),
先用 in-process 内存存根走通。Phase 4 升级到 PostgresStore 时,
只要保持 BaseStore 契约,本测试不变。
"""
from __future__ import annotations

from codeweave.persistence.store import InMemoryStoreShim, make_store, store_search


def test_in_memory_shim_put_and_search_roundtrip():
    s: object = InMemoryStoreShim()
    s.put(("n",), "k1", {"x": 1})  # type: ignore[attr-defined]
    items = list(s.search(("n",)))  # type: ignore[attr-defined]
    assert len(items) == 1
    assert items[0].key == "k1"
    assert items[0].value == {"x": 1}


def test_namespace_isolation():
    s: object = InMemoryStoreShim()
    s.put(("ns-a",), "k", {"a": 1})  # type: ignore[attr-defined]
    s.put(("ns-b",), "k", {"b": 2})  # type: ignore[attr-defined]
    assert len(list(s.search(("ns-a",)))) == 1  # type: ignore[attr-defined]
    assert list(s.search(("ns-a",)))[0].value == {"a": 1}  # type: ignore[attr-defined]


def test_make_store_returns_object_with_search():
    s = make_store()
    items = store_search(s, ("codeweave",), "anything")
    assert isinstance(items, list)