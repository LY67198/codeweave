"""compact_thread Celery task(spec §4.3)。

读 PostgresSaver checkpoint → 调 LLM 摘要 → 写 compact_results。
失败重试 3 次,指数退避。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from codeweave.config.settings import get_settings
from codeweave.db.base import SessionLocal
from codeweave.db.models import CompactResult
from codeweave.persistence.audit import AuditLogger
from codeweave.services.compact_logic import (
    choose_compact_range,
    estimate_messages_tokens,
    render_compact_prompt,
)
from codeweave.services.token_tracker import TokenTracker
from codeweave.tasks._llm import llm_summarize
from codeweave.tasks.celery_app import celery_app

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres import PostgresSaver

logger = logging.getLogger(__name__)
_audit = AuditLogger()
_tracker = TokenTracker()


def _get_checkpointer() -> "PostgresSaver":
    """延迟获取 PostgresSaver,避免 import 时连接数据库。

    Returns:
        LangGraph 原生 :class:`PostgresSaver` 单例。
    """
    from codeweave.persistence.checkpointer import get_checkpointer

    return cast("PostgresSaver", get_checkpointer())  # type: ignore[no-untyped-call]


def _load_pending_compact(session: Session, thread_id: str) -> CompactResult | None:
    """查 ``compact_results`` 里 thread_id + applied=False 的最新一行。

    Args:
        session: SQLAlchemy ``Session``。
        thread_id: 对话/线程 ID。

    Returns:
        已存在的 pending row,或 ``None``。
    """
    return session.execute(
        select(CompactResult)
        .where(
            CompactResult.thread_id == thread_id,
            CompactResult.applied.is_(False),
        )
        .order_by(CompactResult.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="codeweave.compact",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def compact_thread(self: Any, thread_id: str) -> str:
    """Celery task。本身不调 LLM 前先写 audit,成功 / 失败再写一次。

    Args:
        thread_id: 目标 LangGraph thread_id,用于 ``checkpointer.get_state`` 取
            messages 列表。

    Returns:
        写入的 ``compact_results.id``(UUID 字符串);若 nothing-to-compact
        返回空串。
    """
    _audit.emit(
        "compact_started",
        {"messages_total": "?", "tokens_before": 0},
        thread_id=thread_id,
    )

    # 1. 读 messages
    try:
        checkpointer = _get_checkpointer()
        state = checkpointer.get_state(  # type: ignore[attr-defined]
            {"configurable": {"thread_id": thread_id}}
        )
        messages = state.values["messages"]
    except Exception as exc:
        _audit.emit("compact_failed", {"reason": str(exc)}, thread_id=thread_id)
        raise self.retry(exc=exc) from exc

    tokens_before = estimate_messages_tokens(messages)
    settings = get_settings()
    keep_first, keep_last = choose_compact_range(messages, settings.compact_keep_last)
    to_compact = messages[keep_first:keep_last]
    if not to_compact:
        # 没什么可摘要
        _audit.emit(
            "compact_failed",
            {"reason": "nothing_to_compact"},
            thread_id=thread_id,
        )
        return ""

    prompt = render_compact_prompt(
        to_compact,
        keep_last_n=settings.compact_keep_last,
        max_summary_tokens=settings.compact_summary_max_tokens,
    )

    # 2. 调 LLM
    try:
        summary_text, summary_tokens = llm_summarize(prompt, settings)
    except Exception as exc:
        _audit.emit(
            "compact_failed",
            {"reason": str(exc), "retry_count": self.request.retries},
            thread_id=thread_id,
        )
        raise self.retry(exc=exc) from exc

    tokens_after = (
        estimate_messages_tokens(messages[:keep_first])
        + summary_tokens
        + estimate_messages_tokens(messages[keep_last:])
    )

    # 3. 写 compact_results
    row_id = ""
    with SessionLocal() as session:
        try:
            row = _load_pending_compact(session, thread_id)
            if row is None:
                row = CompactResult(thread_id=thread_id, status="pending", applied=False)
                session.add(row)
                session.flush()

            row.summary_message = {"role": "system", "content": summary_text}
            row.keep_first = keep_first
            row.keep_last = keep_last
            row.finished_at = datetime.now(timezone.utc)

            # 有效性检查:压缩后 token 数必须严格小于压缩前,否则标记失败
            if tokens_after >= tokens_before:
                row.status = "failed"
                row.error = "no_reduction"
            else:
                row.status = "done"

            session.commit()
            row_id = str(row.id)
        except Exception:
            session.rollback()
            raise

    _audit.emit(
        "compact_done",
        {
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
        },
        thread_id=thread_id,
    )
    _tracker.track(
        thread_id=thread_id,
        model=settings.model_name,
        prompt_tokens=len(prompt) // 4,  # 粗估
        completion_tokens=summary_tokens,
    )
    return row_id