"""60s 一次扫 token_usage,汇总写到日志(Phase 3 暂不物化 rollups 表)。

(spec §6.2 / §10 Open Question 3)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from codeweave.db.base import SessionLocal
from codeweave.db.models import TokenUsage
from codeweave.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="codeweave.aggregate_token_usage",
)
def aggregate_token_usage() -> dict[str, dict[str, float | int]]:
    """扫过去 60s 的 ``token_usage``,按 model 分组求和,打 info 日志。

    Returns:
        ``{model: {prompt_tokens, completion_tokens, cost_usd}}`` 形式的 dict。
        窗口内无数据时返回空 dict。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
    with SessionLocal() as session:
        rows = session.execute(
            select(
                TokenUsage.model,
                func.sum(TokenUsage.prompt_tokens),
                func.sum(TokenUsage.completion_tokens),
                func.sum(TokenUsage.cost_usd),
            )
            .where(TokenUsage.ts >= cutoff)
            .group_by(TokenUsage.model)
        ).all()
    summary: dict[str, dict[str, float | int]] = {
        model: {
            "prompt_tokens": int(p or 0),
            "completion_tokens": int(c or 0),
            "cost_usd": float(cost or 0),
        }
        for (model, p, c, cost) in rows
    }
    logger.info(
        "token_aggregate_60s",
        extra={"rows": summary, "scanned": len(rows)},
    )
    return summary