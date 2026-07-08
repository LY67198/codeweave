from psycopg_pool import ConnectionPool

from codeweave.config.settings import get_settings


_pool: ConnectionPool | None = None
_saver = None


def _get_pool() -> ConnectionPool:
    """Lazy-init a single shared ConnectionPool."""
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
    """Get PostgresSaver instance from LangGraph (native, no wrappers).

    Uses a shared ConnectionPool so the saver can be passed to graph.compile()
    and live across multiple invocations. Tables are auto-created on first .setup() call.
    """
    global _saver
    if _saver is None:
        from langgraph.checkpoint.postgres import PostgresSaver

        _saver = PostgresSaver(_get_pool())
    return _saver


def setup_checkpointer() -> None:
    """Create checkpoint tables (idempotent). Call once at app startup."""
    get_checkpointer().setup()