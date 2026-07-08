"""init audit / compact / token 表。

Revision ID: 0001
Revises:
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.create_index("ix_audit_events_thread_id", "audit_events", ["thread_id"])
    op.create_index("ix_audit_events_thread_ts", "audit_events", ["thread_id", "ts"])

    op.create_table(
        "compact_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_message", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("keep_first", sa.Integer(), nullable=True),
        sa.Column("keep_last", sa.Integer(), nullable=True),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_compact_results_thread_created", "compact_results", ["thread_id", "created_at"])
    op.create_index(
        "uq_compact_pending_per_thread",
        "compact_results",
        ["thread_id"],
        unique=True,
        postgresql_where=sa.text("applied = false"),
    )

    op.create_table(
        "token_usage",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_token_usage_thread_ts", "token_usage", ["thread_id", "ts"])
    op.create_index("ix_token_usage_ts", "token_usage", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_token_usage_ts", table_name="token_usage")
    op.drop_index("ix_token_usage_thread_ts", table_name="token_usage")
    op.drop_table("token_usage")

    op.drop_index("uq_compact_pending_per_thread", table_name="compact_results")
    op.drop_index("ix_compact_results_thread_created", table_name="compact_results")
    op.drop_table("compact_results")

    op.drop_index("ix_audit_events_thread_ts", table_name="audit_events")
    op.drop_index("ix_audit_events_thread_id", table_name="audit_events")
    op.drop_table("audit_events")
