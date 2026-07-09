"""coder_review_subgraph 状态 schema(spec §3.1)。"""
from __future__ import annotations

from typing import Any, Literal

from typing_extensions import NotRequired, TypedDict


class CodeModState(TypedDict, total=False):
    """Maker/Checker 子图的 TypedDict state。

    所有字段 optional;`request` / `thread_id` 由 router 在 invoke 时注入,
    其余字段由 coder / reviewer / finalize 节点写入。

    Attributes:
        request: 用户的原始修改请求。
        thread_id: LangGraph thread_id,贯穿所有 audit 事件。
        coder_diff: Coder 节点产出的 unified diff 文本。
        coder_message: Coder 节点的工具执行 summary(供前端 SSE 显示)。
        reviewer_decision: Reviewer 节点产出的完整决策 dict。
        retry_count: 已重试次数(首次 invocation 也会被 +1)。
        approved_diff: Reviewer accept 后透传给 finalize 的 diff。
        final_status: finalize 节点产出的最终状态。
        last_feedback: finalize 若 reject 透传出来的最近一次 reviewer 反馈。
    """
    request: str
    thread_id: str

    coder_diff: NotRequired[str]
    coder_message: NotRequired[str]
    reviewer_decision: NotRequired[dict[str, Any]]    # 完整 ReviewerDecision.model_dump()
    retry_count: NotRequired[int]

    approved_diff: NotRequired[str]
    final_status: NotRequired[Literal["approved", "max_retries_exceeded"]]
    last_feedback: NotRequired[str]   # finalize 时若 reject 透传出来,前端可见


__all__ = ["CodeModState"]