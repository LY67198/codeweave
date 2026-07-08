"""End-to-end compact 闭环(celery eager + 真 Postgres + mock LLM)。

序列:
1. mock LLM,准备一段超阈值 messages
2. dispatch compact_thread → 同步执行(task_always_eager)
3. 再次模拟下一个 turn,验证 compact_check.apply 把 summary 写进 state

本测试需要真实 PostgreSQL:
    DATABASE_URL=postgresql+psycopg://codeweave:codeweave_dev@localhost:5432/codeweave_test
执行前请确保 :func:`compact_results` 表已通过 alembic 迁移创建。
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy.exc import OperationalError, DBAPIError

from codeweave.agents._compact_check import decide_compact_action
from codeweave.db.base import SessionLocal
from codeweave.db.models import CompactResult


def _postgres_reachable(url: str, timeout: float = 2.0) -> bool:
    """短超时探测 Postgres 是否可达,避免测试集卡死。"""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine.url import make_url

    try:
        engine = create_engine(
            url,
            connect_args={"connect_timeout": int(timeout)},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (OperationalError, DBAPIError, OSError, ValueError):
        return False


# 集成测试必须依赖真 Postgres;不可达时直接 skip 而不是 hang。
@pytest.fixture(autouse=True)
def require_postgres():
    """若没有可用的 postgres 则跳过整个 e2e。"""
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url:
        pytest.skip("DATABASE_URL not set to a postgres URL")
    if not _postgres_reachable(url):
        pytest.skip(f"Postgres not reachable at {url}")


@pytest.fixture(autouse=True)
def celery_eager():
    """让 Celery 在当前进程同步执行,免去真实 broker。

    进入时打开 ``task_always_eager``,退出时还原,避免污染其他测试。
    """
    from codeweave.tasks.celery_app import celery_app

    prev = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    try:
        yield celery_app
    finally:
        celery_app.conf.task_always_eager = prev


def test_dispatch_then_apply_roundtrip():
    """dispatch 一轮 → 下一 turn 自动 apply,把 summary 嵌回 messages。"""
    settings_mod = pytest.importorskip("codeweave.config.settings")
    _ = settings_mod  # settings 仅在 import 时加载;此处不直接读
    tid = "test-thread-e2e-1"

    # 1) 清旧数据
    with SessionLocal() as session:
        session.query(CompactResult).filter_by(thread_id=tid).delete()
        session.commit()

    # 准备 state 超阈值
    state = {"messages": [HumanMessage(content="x" * 1000)] * 50,
             "thread_id": tid}

    # 2) dispatch path
    def fake_dispatch(thread_id: str) -> str:
        """fake dispatch 回调:同步跑 task body,避免真的去 Celery broker。"""
        with patch("codeweave.tasks.compact.llm_summarize",
                   return_value=("SUMMARY", 50)), \
             patch("codeweave.tasks.compact._get_checkpointer") as ck:
            # _get_checkpointer() → ck 走 get_tuple(PostgresSaver 直 API),
            # 不是 CompiledStateGraph 的 get_state
            ck.return_value.get_tuple.return_value.checkpoint = {
                "channel_values": {"messages": state["messages"]},
            }
            from codeweave.tasks.compact import compact_thread as task_fn
            return task_fn.apply(args=[thread_id]).get()

    action1 = decide_compact_action(
        state, threshold=10, enabled=True, session_factory=SessionLocal,
        dispatch_fn=fake_dispatch, thread_id_getter=lambda s: tid,
    )
    # fake_dispatch 通过 celery eager 同步执行,此时 DB 已有 status=done 行
    assert action1.kind == "dispatch"
    assert action1.compact_id  # 拿到了 compact_results.id

    # 验证 DB 已经写入一条 status=done 的行
    with SessionLocal() as session:
        rows = session.query(CompactResult).filter_by(thread_id=tid).all()
        assert any(r.status == "done" for r in rows)

    # 3) 下一 turn:re-decide 应当走 apply 路径,生成包含 SUMMARY 的 messages
    state_after = {**state, "messages": state["messages"]}
    action2 = decide_compact_action(
        state_after, threshold=10, enabled=True, session_factory=SessionLocal,
        dispatch_fn=fake_dispatch, thread_id_getter=lambda s: tid,
    )
    assert action2.kind == "executor"
    assert action2.new_messages is not None
    assert any("SUMMARY" in m.content for m in action2.new_messages)

    # apply 之后 DB 中该行应该已被标 applied=True
    with SessionLocal() as session:
        rows = session.query(CompactResult).filter_by(thread_id=tid).all()
        assert any(r.applied is True for r in rows)
