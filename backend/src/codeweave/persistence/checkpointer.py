"""LangGraph PostgresSaver 持久化层。

提供基于 ``psycopg_pool.ConnectionPool`` 的共享连接池,以及懒加载的
``PostgresSaver`` 实例,供 ``graph.compile(checkpointer=...)`` 使用。
"""
from psycopg_pool import ConnectionPool

from codeweave.config.settings import get_settings


_pool: ConnectionPool | None = None
_saver = None


def _libpq_dsn(url: str) -> str:
    """把 SQLAlchemy URL 转成 libpq DSN。

    SQLAlchemy 接受 ``postgresql+psycopg://host/...`` 这种带 dialect
    前缀的 URL,而 :class:`psycopg_pool.ConnectionPool` 的 ``conninfo``
    直接交给 libpq,libpq 不认识 ``+psycopg`` 后缀,会报
    ``missing "=" after "postgresql+psycopg://..."``。
    这里简单剥掉 dialect 中缀,保留 ``postgresql://`` 给 libpq 解析。
    """
    if url.startswith("postgresql+") and "://" in url:
        return "postgresql://" + url.split("://", 1)[1]
    return url


def _get_pool() -> ConnectionPool:
    """延迟初始化一个共享的 ConnectionPool。

    使用模块级单例,首次调用时根据 ``Settings.database_url`` 创建,
    之后复用同一实例。连接池 ``min_size=1``、``max_size=5``,
    并开启 ``autocommit``。

    Returns:
        全局共享的 ``ConnectionPool`` 实例。
    """
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            conninfo=_libpq_dsn(settings.database_url),
            min_size=1,
            max_size=5,
            kwargs={"autocommit": True},
        )
    return _pool


def get_checkpointer():
    """获取 LangGraph 原生的 PostgresSaver 实例(无额外封装)。

    使用共享的 ``ConnectionPool``,以便将 saver 传递给 ``graph.compile()``,
    并在多次调用之间复用。表会在首次调用 ``.setup()`` 时自动创建。

    Returns:
        懒加载的 ``PostgresSaver`` 单例。
    """
    global _saver
    if _saver is None:
        from langgraph.checkpoint.postgres import PostgresSaver

        _saver = PostgresSaver(_get_pool())
    return _saver


def setup_checkpointer() -> None:
    """创建 checkpoint 表(幂等操作)。请在应用启动时调用一次。

    Returns:
        无返回值。
    """
    get_checkpointer().setup()