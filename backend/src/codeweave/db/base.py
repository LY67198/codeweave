"""SQLAlchemy 2.x engine + Session 工厂。

所有 DB 写入路径统一调 :func:`get_session()` 上下文管理器。
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from codeweave.config.settings import get_settings


class Base(DeclarativeBase):
    """所有 ORM 模型的 declarative 基类。"""


def _build_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        future=True,
    )


engine: Engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def get_session() -> Iterator[Session]:
    """事务化的 Session 上下文管理器。

    Yields:
        SQLAlchemy ``Session``。退出 with 块时若无异常则 commit,有异常则 rollback。
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()