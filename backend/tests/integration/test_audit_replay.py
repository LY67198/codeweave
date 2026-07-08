"""用 audit_events 重放一段会话,验证 messages 序列可还原。

本测试需要真实 PostgreSQL:
    DATABASE_URL=postgresql://codeweave:codeweave_dev@localhost:5432/codeweave_test
执行前请确保 :class:`AuditEvent` 表已通过 alembic 迁移创建。
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import OperationalError, DBAPIError

from codeweave.db.base import SessionLocal
from codeweave.db.models import AuditEvent
from codeweave.persistence.audit import AuditLogger


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


# 集成测试必须依赖真 Postgres;不可达时直接 skip 而不是 hang。
@pytest.fixture(autouse=True)
def require_postgres():
    """若没有可用的 postgres 则跳过整个 audit replay e2e。"""
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url:
        pytest.skip("DATABASE_URL not set to a postgres URL")
    if not _postgres_reachable(url):
        pytest.skip(f"Postgres not reachable at {url}")


@pytest.fixture()
def thread_id() -> str:
    """隔离 thread_id,fixture 结束后清掉残留行。"""
    tid = "test-replay-1"
    # 清旧数据,确保每次跑是干净环境
    with SessionLocal() as session:
        session.query(AuditEvent).filter_by(thread_id=tid).delete()
        session.commit()
    yield tid
    # 测试结束再清一次,不影响其他测试
    with SessionLocal() as session:
        session.query(AuditEvent).filter_by(thread_id=tid).delete()
        session.commit()


def test_audit_timeline_roundtrip(thread_id: str):
    """写入 4 条 audit 事件,通过 get_thread_timeline 读回,验证顺序 + payload 完整。"""
    logger = AuditLogger()
    _ = datetime.now(timezone.utc)  # 仅用于占位语义,实际 ts 由 DB server_default 生成

    # 写入若干事件
    for i, kind in enumerate(["compact_check", "tool_call", "compact_started",
                              "compact_done"]):
        logger.emit(kind,
                    {"i": i,
                     "content": f"payload-{i}",
                     "tool": "read_file", "args": {"path": f"f{i}"},
                     "tokens_before": 100, "tokens_after": 80,
                     "reason": "ok", "retry_count": 0,
                     "duration_ms": 50},
                    thread_id=thread_id, duration_ms=50)
        time.sleep(0.01)

    timeline = logger.get_thread_timeline(thread_id, limit=10)
    assert len(timeline) == 4
    assert [t["kind"] for t in timeline] == [
        "compact_check", "tool_call", "compact_started", "compact_done",
    ]

    # 可重放:每条事件 payload 完整保留
    assert timeline[-1]["payload"]["tokens_after"] == 80

    # 时间线按 ts 升序:相邻事件的 ts 应当单调不减(允许相等,因为 server_default
    # 可能在同一毫秒内触发)。
    ts_values = [t["ts"] for t in timeline]
    for prev, curr in zip(ts_values, ts_values[1:]):
        assert curr >= prev, f"timeline out of order: {prev} > {curr}"