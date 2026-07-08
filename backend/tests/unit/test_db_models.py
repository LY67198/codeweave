"""验证 ORM 模型字段定义与 spec §3 完全一致。"""
from sqlalchemy import inspect

from codeweave.db.base import Base
from codeweave.db.models import AuditEvent, CompactResult, TokenUsage


def test_audit_events_table_columns():
    cols = {c.name: c for c in inspect(AuditEvent).columns}
    assert set(cols) == {"id", "thread_id", "ts", "kind", "payload", "duration_ms"}
    assert cols["thread_id"].nullable is False
    assert cols["kind"].nullable is False


def test_compact_results_table_columns_and_indexes():
    cols = {c.name: c for c in inspect(CompactResult).columns}
    assert set(cols) == {
        "id", "thread_id", "status", "created_at",
        "finished_at", "summary_message", "keep_first",
        "keep_last", "applied", "error",
    }

    # inspect(Model) → Mapper (SQLAlchemy 2.x); use inspect(Model.__table__) to
    # reach the underlying Table and its indexes. Index objects expose
    # ``dialect_options`` as a nested dict-style structure whose ``postgresql``
    # entry holds a ``where`` clause (TextClause) for partial-unique indexes.
    indexes = inspect(CompactResult.__table__).indexes
    partial = next(
        (i for i in indexes
         if "postgresql" in i.dialect_options
         and "where" in i.dialect_options["postgresql"]),
        None,
    )
    assert partial is not None, "应存在 applied=false 的部分唯一索引"


def test_token_usage_table_columns():
    cols = {c.name: c for c in inspect(TokenUsage).columns}
    assert set(cols) == {"id", "thread_id", "ts", "model",
                         "prompt_tokens", "completion_tokens", "cost_usd"}


def test_all_models_registered_with_metadata():
    tables = set(Base.metadata.tables)
    assert {"audit_events", "compact_results", "token_usage"} <= tables
