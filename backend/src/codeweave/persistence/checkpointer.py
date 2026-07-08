from psycopg_pool import ConnectionPool

from codeweave.config.settings import get_settings


_pool: ConnectionPool | None = None
_saver = None


def _get_pool() -> ConnectionPool:
    """延迟初始化一个共享的 ConnectionPool。"""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=5,
            kwargs={"autocommit": True},
        )
    return _pool


def get_checkpointer():
    """获取 LangGraph 原生的 PostgresSaver 实例（无额外封装）。

    使用共享的 ConnectionPool，以便将 saver 传递给 graph.compile()，
    并在多次调用之间复用。表会在首次调用 .setup() 时自动创建。
    """
    global _saver
    if _saver is None:
        from langgraph.checkpoint.postgres import PostgresSaver

        _saver = PostgresSaver(_get_pool())
    return _saver


def setup_checkpointer() -> None:
    """创建 checkpoint 表（幂等操作）。请在应用启动时调用一次。"""
    get_checkpointer().setup()