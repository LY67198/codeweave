"""Compact 节点群(spec §4)。

- :func:`compact_check_node` graph 入口,跑 ``decide_compact_action`` 后翻译为 state 更新。
- :func:`compact_node` 占位保留(向后兼容,Phase 4 时删)。

设计原则:把决策逻辑抽到 ``codeweave.agents._compact_check`` 做纯函数,节点函数本
身体薄,只做翻译 + 副作用(Celery dispatch + Audit)。
"""
from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from codeweave.agents._compact_check import decide_compact_action
from codeweave.config.settings import get_settings
from codeweave.db.base import get_session
from codeweave.persistence.audit import AuditLogger
from codeweave.state.schemas import RootState
from codeweave.tasks.compact import compact_thread

_audit = AuditLogger()


def compact_check_node(
    state: RootState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """每个 turn 入口检查是否需要 compact,并 apply / dispatch / skip。

    使用 :func:`codeweave.agents._compact_check.decide_compact_action` 做纯决策,
    本函数只负责翻译为 state 更新,并触发 Celery 派发与 audit 事件。

    Args:
        state: 当前 graph state。
        config: LangGraph RunnableConfig,用于回退读取 ``thread_id``。

    Returns:
        描述状态变更的 dict(可能为空)。``next_agent="__end__"`` 表示本 turn
        不再流转(supervisor 不会再被叫起)。
    """
    settings = get_settings()
    thread_id = (
        state.get("thread_id")
        or (config or {}).get("configurable", {}).get("thread_id")
        or "<unknown>"
    )

    def _dispatch(tid: str) -> str:
        """触发 Celery 任务并返回 compact_id(UUID 字符串)。"""
        async_result = compact_thread.delay(tid)
        return str(async_result.id)

    action = decide_compact_action(
        state,  # type: ignore[arg-type]
        threshold=settings.compact_threshold,
        enabled=settings.compact_enabled,
        session_factory=get_session,
        dispatch_fn=_dispatch,
        thread_id_getter=lambda s: thread_id,
    )

    _audit.emit(
        "compact_check",
        {"decision": action.kind, "compact_id": action.compact_id},
        thread_id=thread_id,
    )

    if action.kind == "skip":
        return {}
    if action.kind == "executor":
        out: dict[str, Any] = {}
        if action.new_messages is not None:
            out["messages"] = action.new_messages
            out["compact_pending"] = False
        return out
    if action.kind == "__end__":
        return {
            "compact_pending": action.compact_pending,
            "last_dispatched_compact_id": action.compact_id,
            "messages": [],  # 不增加新内容
            "next_agent": "__end__",
        }
    if action.kind == "dispatch":
        return {
            "compact_pending": True,
            "last_dispatched_compact_id": action.compact_id,
            "next_agent": "__end__",
        }
    # 未知 kind,兜底返回空,避免 graph 崩溃
    return {}


# 占位保留(向后兼容,Phase 4 删除)
def compact_node(state: RootState) -> dict[str, Any]:
    """Compact 节点占位实现。

    Args:
        state: 当前 graph state。

    Returns:
        包含 ``messages`` 的部分 state 更新,目前为空消息列表。
    """
    return {"messages": []}
