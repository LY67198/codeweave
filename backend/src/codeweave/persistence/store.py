"""长时记忆 Store 层(spec §5.1)。

Phase 3 默认用 InMemoryStoreShim(in-process + 线程安全),
Phase 4 升级到 ``langgraph-checkpoint-postgres`` 提供的 ``PostgresStore``
时仅需把 :func:`make_store` 改成构建 PostgresStore 实例,接口不变。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Iterable, Protocol


@dataclass
class StoreItem:
    """搜索 / 读取的统一返回类型。

    Attributes:
        key: 条目的键(在 namespace 内唯一)。
        value: 条目的值(任意可 JSON 序列化的对象)。
        namespace: 条目所属的命名空间(以元组形式存储)。
    """
    key: str
    value: Any
    namespace: tuple[str, ...]


class BaseStoreLike(Protocol):
    """LangGraph BaseStore 兼容协议(子集)。

    任何满足该协议的对象都可以作为 :func:`store_search` 的输入,
    这样 Phase 4 替换为 ``PostgresStore`` 时无需修改调用方。
    """
    def put(self, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None: ...
    def get(self, namespace: tuple[str, ...], key: str) -> StoreItem | None: ...
    def search(self, namespace_prefix: tuple[str, ...],
               *, limit: int = 10) -> Iterable[StoreItem]: ...
    def delete(self, namespace: tuple[str, ...], key: str) -> None: ...


class InMemoryStoreShim:
    """内存版 Store;Phase 3 阶段用此保证可测试。线程安全。

    所有操作都在 :class:`threading.Lock` 保护下进行,可被多线程访问。
    Phase 4 替换为 ``PostgresStore`` 时此实现会被 :func:`make_store`
    工厂切换,但 :class:`BaseStoreLike` 协议保持不变。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (namespace, key) -> value
        self._data: dict[tuple[tuple[str, ...], str], Any] = {}

    def put(self, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None:
        """写入一个 (namespace, key) -> value 映射。

        Args:
            namespace: 命名空间,以元组形式传入(支持嵌套层级)。
            key: 命名空间内的唯一键。
            value: 任意可序列化的 Python 对象。
        """
        with self._lock:
            self._data[(tuple(namespace), key)] = value

    def get(self, namespace: tuple[str, ...], key: str) -> StoreItem | None:
        """按 (namespace, key) 取值。

        Args:
            namespace: 命名空间。
            key: 键。

        Returns:
            找到则返回 :class:`StoreItem`,否则返回 ``None``。
        """
        with self._lock:
            value = self._data.get((tuple(namespace), key))
            if value is None:
                return None
            return StoreItem(key=key, value=value, namespace=tuple(namespace))

    def search(self, namespace_prefix: tuple[str, ...], *,
               limit: int = 10) -> list[StoreItem]:
        """按命名空间前缀搜索条目。

        匹配规则:条目 namespace 的前 ``len(namespace_prefix)`` 段
        与 ``namespace_prefix`` 完全相等即命中。结果按 key 排序后
        截断到 ``limit`` 条。

        Args:
            namespace_prefix: 命名空间前缀。
            limit: 返回的最大条目数。

        Returns:
            匹配的 :class:`StoreItem` 列表(已排序 + 截断)。
        """
        with self._lock:
            out = [
                StoreItem(key=k, value=v, namespace=ns)
                for (ns, k), v in self._data.items()
                if tuple(ns)[: len(namespace_prefix)] == tuple(namespace_prefix)
            ]
            out.sort(key=lambda x: x.key)
            return out[:limit]

    def delete(self, namespace: tuple[str, ...], key: str) -> None:
        """删除一个 (namespace, key) 映射。

        如果条目不存在则什么都不做(``dict.pop`` 默认行为)。

        Args:
            namespace: 命名空间。
            key: 键。
        """
        with self._lock:
            self._data.pop((tuple(namespace), key), None)


def make_store() -> BaseStoreLike:
    """构造 Store 实例。

    返回值满足 :class:`BaseStoreLike` 协议即可;Phase 4 可替换为 PostgresStore。
    """
    return InMemoryStoreShim()


def store_search(
    store: BaseStoreLike,
    namespace: tuple[str, ...],
    query: str | None = None,
    *,
    limit: int = 10,
) -> list[StoreItem]:
    """简化调用:Phase 3 内文本 query 不参与过滤,仅用作日志上下文。

    Args:
        store: 满足 :class:`BaseStoreLike` 协议的 Store 实例。
        namespace: 命名空间前缀。
        query: 可选的文本查询(Phase 3 暂未使用,预留给 Phase 4 的向量检索)。
        limit: 返回的最大条目数。

    Returns:
        匹配的 :class:`StoreItem` 列表。
    """
    _ = query  # 预留接口
    return list(store.search(namespace, limit=limit))