"""GET /state /timeline /cost 路由(spec §2.1)。

提供:
- ``GET /threads/{thread_id}/state`` — 当前 checkpoint 全量;
- ``GET /threads/{thread_id}/timeline`` — audit_events 时间线;
- ``GET /cost`` — token 用量按模型聚合(最近 60s 窗口)。

``/state`` 通过 PostgresSaver ``get_tuple`` 拉取最近一个 checkpoint,
``/timeline`` / ``/cost`` 直接走 SQLAlchemy SessionLocal 读 DB。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import anyio
from fastapi import APIRouter, Request
from sqlalchemy import func, select

from codeweave.api.errors import ApiError
from codeweave.api.models.cost import CostByModel, CostEntry
from codeweave.api.models.threads import ThreadState, TimelineResponse
from codeweave.db.base import SessionLocal
from codeweave.db.models import AuditEvent, TokenUsage


router = APIRouter(tags=["queries"])


@router.get(
    "/threads/{thread_id}/state",
    response_model=ThreadState,
    summary="拉当前 checkpoint 全量",
)
async def get_state(thread_id: str, request: Request) -> ThreadState:
    """读 PostgresSaver 最近一个 checkpoint,组装 ThreadState。

    Args:
        thread_id: thread 主键(path param)。
        request: FastAPI request,从中取 lifespan 注入的 ``checkpointer``。

    Returns:
        当前 checkpoint 的 ThreadState(messages / todos / plan_mode /
        agent_history / compact_pending / last_dispatched_compact_id)。

    Raises:
        ApiError: thread 在 checkpointer 里无任何 checkpoint,404 ``not_found``。
    """
    checkpointer = request.app.state.checkpointer
    config = {"configurable": {"thread_id": thread_id}}
    state_tuple = await anyio.to_thread.run_sync(
        checkpointer.get_tuple, config
    )
    if state_tuple is None:
        raise ApiError(
            code="not_found",
            message=f"thread {thread_id} 在 PostgresSaver 里无任何 checkpoint",
            status_code=404,
        )
    chk = state_tuple.checkpoint or {}
    cv = chk.get("channel_values", {})
    return ThreadState(
        thread_id=thread_id,
        messages=[
            {
                "type": getattr(m, "type", m.__class__.__name__),
                "content": getattr(m, "content", ""),
            }
            for m in cv.get("messages", [])
        ],
        todos=list(cv.get("todos", [])),
        plan_mode=bool(cv.get("plan_mode", True)),
        agent_history=list(cv.get("agent_history", [])),
        compact_pending=bool(cv.get("compact_pending", False)),
        last_dispatched_compact_id=cv.get("last_dispatched_compact_id"),
    )


@router.get(
    "/threads/{thread_id}/timeline",
    response_model=TimelineResponse,
    summary="audit_events 时间线",
)
async def get_timeline(thread_id: str) -> TimelineResponse:
    """读 audit_events 表倒序最近 200 条,按时间正序返回。

    Args:
        thread_id: thread 主键(path param)。

    Returns:
        ``TimelineResponse``,``events`` 是按 ts 升序的 dict 列表。
    """
    with SessionLocal() as s:
        rows = (
            s.query(AuditEvent)
            .filter_by(thread_id=thread_id)
            .order_by(AuditEvent.ts.desc())
            .limit(200)
            .all()
        )
        events = [
            {
                "id": r.id,
                "ts": r.ts.isoformat(),
                "kind": r.kind,
                "payload": r.payload,
                "duration_ms": r.duration_ms,
            }
            for r in reversed(rows)
        ]
    return TimelineResponse(thread_id=thread_id, events=events)


@router.get(
    "/cost",
    response_model=CostByModel,
    summary="按模型聚合 token 用量",
)
async def get_cost() -> CostByModel:
    """聚合最近 60 秒的 token_usage,按 model 维度求和。

    Returns:
        ``CostByModel``,``since`` 是窗口起点,``by_model`` 是 model → ``CostEntry``。
    """
    since = datetime.now(tz=timezone.utc) - timedelta(seconds=60)
    with SessionLocal() as s:
        rows = s.execute(
            select(
                TokenUsage.model,
                func.sum(TokenUsage.prompt_tokens),
                func.sum(TokenUsage.completion_tokens),
                func.sum(TokenUsage.cost_usd),
            )
            .where(TokenUsage.ts >= since)
            .group_by(TokenUsage.model)
        ).all()
    by_model: dict[str, CostEntry] = {}
    for model, p, c, cost in rows:
        by_model[str(model)] = CostEntry(
            prompt_tokens=int(p or 0),
            completion_tokens=int(c or 0),
            cost_usd=float(cost or 0),
        )
    return CostByModel(since=since, by_model=by_model)