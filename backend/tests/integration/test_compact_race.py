"""并发 dispatch 竞态测试。

8 个线程同时调 :func:`decide_compact_action`,验证:
1. 由于 ``uq_compact_pending_per_thread`` 部分唯一索引(``applied=false``),
   只有一个线程的 INSERT 能成功。
2. 其它线程拿到 ``IntegrityError`` 后被退化为 ``kind="__end__"``。
3. 最终 DB 中该 thread 仅 1 条 ``applied=False`` 的行。
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy.exc import OperationalError, DBAPIError

from codeweave.agents._compact_check import decide_compact_action
from codeweave.db.base import SessionLocal
from codeweave.db.models import CompactResult


def _postgres_reachable(url: str, timeout: float = 2.0) -> bool:
    """短超时探测 Postgres 是否可达,避免测试集卡死。"""
    from sqlalchemy import create_engine

    try:
        engine = create_engine(
            url,
            connect_args={"connect_timeout": int(timeout)},
        )
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except (OperationalError, DBAPIError, OSError, ValueError):
        return False


@pytest.fixture(autouse=True)
def require_postgres():
    """若没有可用的 postgres 则跳过整个竞态测试。"""
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url:
        pytest.skip("DATABASE_URL not set to a postgres URL")
    if not _postgres_reachable(url):
        pytest.skip(f"Postgres not reachable at {url}")


def test_concurrent_compact_dispatch_creates_only_one_pending():
    """两个 turn 并发 dispatch,部分唯一索引保证只产生一条 pending。"""
    tid = "test-thread-race-1"
    state = {"messages": [HumanMessage(content="y" * 5000)] * 100,
             "thread_id": tid}

    # 清旧数据,保证 partial unique index 不被历史脏数据干扰
    with SessionLocal() as session:
        session.query(CompactResult).filter_by(thread_id=tid).delete()
        session.commit()

    def fake_dispatch(_tid: str) -> str:
        """race 测试不需要真的调 Celery,直接返回 ID 占位。"""
        return "noop-id"

    def run_one():
        return decide_compact_action(
            state, threshold=10, enabled=True, session_factory=SessionLocal,
            dispatch_fn=fake_dispatch, thread_id_getter=lambda s: tid,
        )

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(lambda _: run_one(), range(8)))

    # 8 个并发调用,只有一个应该是 dispatch(其它都是 __end__)
    kinds = [r.kind for r in results]
    assert kinds.count("dispatch") == 1
    assert kinds.count("__end__") == 7

    with SessionLocal() as session:
        pending = session.query(CompactResult).filter_by(
            thread_id=tid, applied=False,
        ).all()
        assert len(pending) == 1
