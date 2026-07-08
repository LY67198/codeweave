"""每周一次清理 ``compact_results`` 中已 apply 且超过保留天数的行(spec §3.6)。

``retention_days=0`` 表示全部清,主要给测试用。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from codeweave.config.settings import get_settings
from codeweave.db.base import SessionLocal
from codeweave.db.models import CompactResult
from codeweave.tasks.celery_app import celery_app


@celery_app.task(  # type: ignore[untyped-decorator]
    name="codeweave.cleanup_old_compact_results",
)
def cleanup_old_compact_results(retention_days: int | None = None) -> int:
    """删除 ``applied=True`` 且 ``finished_at < now - retention`` 的行。

    Args:
        retention_days: 保留天数,``None`` 时读 settings 的
            ``compact_cleanup_retention_days``(默认 7);传 ``0`` 表示全部清理。

    Returns:
        被删除的行数(由 SQLAlchemy ``Result.rowcount`` 提供)。
    """
    days = (
        retention_days
        if retention_days is not None
        else get_settings().compact_cleanup_retention_days
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with SessionLocal() as session:
        stmt = delete(CompactResult).where(
            CompactResult.applied == True,  # noqa: E712
            CompactResult.finished_at.is_not(None),
            CompactResult.finished_at < cutoff,
        )
        result = session.execute(stmt)
        session.commit()
        rowcount: int = getattr(result, "rowcount", 0) or 0
        return int(rowcount)