"""Phase 3 新增的 ORM 模型。

所有表 schema 在 spec §3 已经定义。本文件只描述 SQLAlchemy 映射,具体 SQL
由 Alembic migration 0001 创建。
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from codeweave.db.base import Base


class AuditEvent(Base):
    """可追加时间线日志(spec §3.1)。"""
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    ts: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_audit_events_thread_ts", "thread_id", "ts"),
    )


class CompactResult(Base):
    """Compact 尝试历史 + 待合并队列(spec §3.2)。"""
    __tablename__ = "compact_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    summary_message: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    keep_first: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keep_last: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_compact_results_thread_created", "thread_id", "created_at"),
        # 部分唯一索引:每个 thread 最多一个"待合并"行
        Index(
            "uq_compact_pending_per_thread",
            "thread_id",
            unique=True,
            postgresql_where=text("applied = false"),
        ),
    )


class TokenUsage(Base):
    """单次 LLM 调用的 token 用量(spec §3.3)。"""
    __tablename__ = "token_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 6), nullable=False, default=0,
    )

    __table_args__ = (
        Index("ix_token_usage_thread_ts", "thread_id", "ts"),
        Index("ix_token_usage_ts", "ts"),
    )
