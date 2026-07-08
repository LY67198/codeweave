"""compact_check 决策纯逻辑(spec §4.2)。

返回 :class:`CompactAction`,由 graph 节点薄调用 translation 为 state 更新。
本模块与 LangGraph / Celery 完全解耦,便于单测覆盖边界。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

from langchain_core.messages import AIMessage, BaseMessage
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from codeweave.db.models import CompactResult
from codeweave.services.compact_logic import estimate_messages_tokens

ActionKind = Literal["skip", "executor", "__end__", "dispatch"]


@dataclass
class CompactAction:
    """compact_check 决策结果。

    Attributes:
        kind: 决策类型。``skip`` = 跳过本节点;``executor`` = 流转到 executor
            (可能带 ``new_messages`` 用于 apply 已完成摘要);``__end__`` =
            本次不流转,等下一 turn;``dispatch`` = 本次触发了 Celery dispatch。
        compact_pending: dispatch 后是否处于"已派发未 apply"的状态。
        compact_id: 本次分派或获取的 compact ID(UUID 字符串),可能为 None。
        new_messages: 用于 replace 当前 messages 的新列表(apply 路径),
            可能为 None。
    """
    kind: ActionKind
    compact_pending: bool = False
    compact_id: str | None = None
    new_messages: list[BaseMessage] | None = None


class _SessionFactory(Protocol):
    """Session 上下文管理器工厂的类型协议。"""
    def __call__(self) -> Any: ...


def decide_compact_action(
    state: dict[str, Any],
    *,
    threshold: int,
    enabled: bool,
    session_factory: _SessionFactory,
    dispatch_fn: Callable[[str], str],
    thread_id_getter: Callable[[dict[str, Any]], str],
) -> CompactAction:
    """核心决策流程,无 graph / 无 Celery 副作用。

    决策顺序(优先级从高到低):
        1. HITL ``__interrupt__`` 已设置 → ``skip``
        2. 全局 ``enabled=False`` → ``skip``
        3. 查到 ``status="done"`` 的 compact 行 → ``executor`` + apply(替换 messages)
        4. 查到 ``applied=False`` 的 pending 行 → ``__end__``
        5. token 数未超阈值 → ``executor``
        6. 超阈值 → INSERT 新 pending 行 + ``dispatch_fn`` 触发 Celery

    Args:
        state: 当前 LangGraph state(支持 ``__interrupt__`` 与 ``messages`` key)。
        threshold: 触发 compact 的 token 阈值。
        enabled: compact 总开关。
        session_factory: 返回 Session 上下文管理器的工厂。
        dispatch_fn: 触发 Celery 任务的回调,接收 ``thread_id`` 返回
            ``compact_id``。纯逻辑不直接依赖 Celery。
        thread_id_getter: 从 state 提取 ``thread_id`` 的回调。

    Returns:
        :class:`CompactAction` 描述下一步该做什么。
    """
    # ① HITL resume 跳过(HITL 期间不抢 compact 入口)
    if state.get("__interrupt__"):
        return CompactAction(kind="skip")

    # ② 全局禁用
    if not enabled:
        return CompactAction(kind="skip")

    thread_id = thread_id_getter(state)

    # ③ 查 compact_results 行
    with session_factory() as session:
        # 先查 done(优先级高于 pending —— 已完成但未 apply 应立即 apply)
        done = session.execute(
            select(CompactResult)
            .where(
                CompactResult.thread_id == thread_id,
                CompactResult.status == "done",
                CompactResult.applied == False,  # noqa: E712
            )
        ).scalar_one_or_none()

        if done is not None:
            old = state["messages"]
            new = (
                list(old[: done.keep_first])
                + [AIMessage(content=done.summary_message["content"])]
                + list(old[done.keep_last:])
            )
            done.applied = True
            return CompactAction(
                kind="executor",
                new_messages=new,
                compact_pending=False,
            )

        # 再查 pending(已派发但 Celery 还没写完或写完但还没被检测到 done)
        pending = session.execute(
            select(CompactResult)
            .where(
                CompactResult.thread_id == thread_id,
                CompactResult.applied == False,  # noqa: E712
            )
        ).scalar_one_or_none()

        if pending is not None:
            return CompactAction(kind="__end__")

    # ④ 阈值判定(都已处理完毕,正常流转)
    messages = state["messages"]
    if estimate_messages_tokens(messages) <= threshold:
        return CompactAction(kind="executor")

    # ⑤ 超阈值 → dispatch
    with session_factory() as session:
        try:
            row = CompactResult(
                thread_id=thread_id,
                status="pending",
                applied=False,
            )
            session.add(row)
            session.flush()
        except IntegrityError:
            # 唯一索引撞了 → 已有 pending 行在并发中被别人插入
            session.rollback()
            return CompactAction(kind="__end__")

    new_id = dispatch_fn(thread_id)  # Celery .delay,返回 compact_id
    return CompactAction(
        kind="dispatch",
        compact_pending=True,
        compact_id=new_id,
    )
