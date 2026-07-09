"""POST /api/v1/threads/{id}/code-mod SSE 路由(spec §5)。

面向客户端的 Code-Mod(Maker/Checker)入口:
- ``POST /threads/{thread_id}/code-mod``:接收 user 请求,推动
  ``coder_review_subgraph`` 跑 Coder ↔ Reviewer 循环,把中间状态用
  SSE 推给前端,最后发 ``done`` 事件(approved_diff / final_status)。

并发保护:同 thread 已有 in-flight 流就 409,避免 LangGraph
checkpointer 的 race 条件(进程内 ``_active_streams`` 字典实现,
Phase 4 messages router 的同款)。

``_run_coder_review`` 是一个独立可 mock 的薄封装:test 用
``unittest.mock.patch`` 替换它即可注入假决策,无需建立真实
Coder/Reviewer graph 流水线。``_run_coder_review`` 返回最终状态
字典(包含 ``approved_diff`` / ``final_status`` / ``reviewer_decision``),
然后 ``_stream`` generator 仅 yield ``done`` 事件 — 单 chunk,
不暴露中间 Coder/Reviewer 步骤细节(spec §5)。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Request
from sse_starlette.event import ServerSentEvent
from sse_starlette.sse import EventSourceResponse

from codeweave.api.deps import get_audit, get_trace_id
from codeweave.api.errors import ApiError
from codeweave.api.models.threads import StreamEvent
from codeweave.graphs.coder_review_graph import build_coder_review_graph
from codeweave.persistence.audit import AuditLogger
from codeweave.skills.state import CodeModState


router = APIRouter(prefix="/threads/{thread_id}", tags=["code_mod"])


# 进程内 in-flight stream registry(thread_id → asyncio.Event)。
# 与 Phase 4 messages router 同模式,Phase 7 可换 Redis flag。
_active_streams: dict[str, asyncio.Event] = {}


def _acquire_stream_slot(thread_id: str) -> asyncio.Event:
    """抢占同 thread 的 in-flight stream slot,已有则 409。

    Args:
        thread_id: thread 主键。

    Returns:
        持有的 release event,stream 结束后由 ``_release_stream_slot`` set。

    Raises:
        ApiError: 同 thread 已有 in-flight 流时,抛 409 ``thread_already_active``。
    """
    if thread_id in _active_streams:
        raise ApiError(
            code="thread_already_active",
            message=f"thread {thread_id} 已有 code-mod 在进行",
            status_code=409,
        )
    ev = asyncio.Event()
    _active_streams[thread_id] = ev
    return ev


def _release_stream_slot(thread_id: str, ev: asyncio.Event) -> None:
    """释放 slot:仅在 ev 仍是当前 owner 时才 set + pop,避免误释放别人的 slot。

    Args:
        thread_id: thread 主键。
        ev: ``_acquire_stream_slot`` 返回的 event。
    """
    if _active_streams.get(thread_id) is ev:
        _active_streams.pop(thread_id, None)
        ev.set()


def _get_compiled_graph(request: Request, thread_id: str) -> Any:
    """从 ``app.state.graph_cache`` 取该 thread 的编译图(线程安全 LRU)。

    Per-thread cache(与 Phase 4 messages router 一致),跨 thread 复用同一
    编译图,避免每次请求重建;checkpointer / store 由 lifespan 持有。

    Args:
        request: FastAPI 请求对象,用于 DI cache 读取。
        thread_id: thread 主键。

    Returns:
        编译好的 LangGraph 图,已挂上 lifespan 注入的 checkpointer。
    """
    cache = request.app.state.graph_cache
    if thread_id not in cache:
        cache[thread_id] = build_coder_review_graph().compile(
            checkpointer=request.app.state.checkpointer,
        )
    return cache[thread_id]


def _run_coder_review(
    graph: Any,
    config: dict[str, Any],
    input_dict: CodeModState,
) -> dict[str, Any]:
    """执行 coder_review_subgraph 并返回最终决策 dict。

    这是 router 层注入 seam — test 用 ``patch`` 替换它即可绕开真实
    graph 执行(避免 LLM 调用 + DB 读写)。生产路径直接 ``graph.stream``
    同步跑一遍(单次 invoke 即可,无中断路径),把最后 chunk 折叠成
    ``approved_diff`` / ``final_status`` / ``reviewer_decision`` 字典。

    Args:
        graph: 编译好的 LangGraph 图。
        config: LangGraph ``configurable.thread_id`` 配置。
        input_dict: 推入 graph 的初始 ``CodeModState``。

    Returns:
        含 ``approved_diff`` / ``final_status`` / ``reviewer_decision`` 的最终决策 dict。
    """
    final_chunk: dict[str, Any] = {}
    for chunk in graph.stream(input_dict, config=config, stream_mode="updates"):
        # chunk 是 ``{<node>: <state_update>}`` 形态
        for _node, update in chunk.items():
            if isinstance(update, dict):
                final_chunk.update(update)
    return {
        "approved_diff": final_chunk.get("approved_diff"),
        "final_status": final_chunk.get("final_status", "max_retries_exceeded"),
        "reviewer_decision": final_chunk.get("reviewer_decision", {}),
    }


async def _stream_code_mod(
    graph: Any,
    config: dict[str, Any],
    input_dict: CodeModState,
    thread_id: str,
    trace_id: str,
    audit: AuditLogger,
) -> AsyncIterator[ServerSentEvent]:
    """跑 coder_review_subgraph 并把最终结果折成单条 done SSE 事件。

    内部用 ``asyncio.Queue`` + executor 把同步 ``_run_coder_review``
    异步化。SSE 形态 spec §5:每条 ``ServerSentEvent`` 带 ``event`` 字段
    和 ``data: <json>`` 字段,前端据此分发到 UI 状态机。

    Args:
        graph: 编译好的 LangGraph 图。
        config: LangGraph 配置。
        input_dict: ``CodeModState`` 输入。
        thread_id: thread 主键,塞进每个 event 上下文。
        trace_id: 贯穿请求追踪 id。
        audit: AuditLogger,中间错误会写 audit。

    Yields:
        ``ServerSentEvent``,最后一条 event 是 ``done``。
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=8)
    SENTINEL = object()

    def _run_sync() -> None:
        try:
            result = _run_coder_review(graph, config, input_dict)
            loop.call_soon_threadsafe(queue.put_nowait, result)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, SENTINEL)

    loop.run_in_executor(None, _run_sync)

    chunk = await queue.get()
    if isinstance(chunk, Exception):
        audit.emit(
            "api_coder_review_failed",
            {"error": str(chunk), "error_type": type(chunk).__name__},
            thread_id=thread_id,
        )
        # 把错误折成 error event,前端可见;然后仍发 done 让前端 UI 关闭
        err_evt = StreamEvent(
            event="error",
            thread_id=thread_id,
            data={"error": str(chunk)},
            trace_id=trace_id,
        )
        yield ServerSentEvent(
            data=json.dumps(err_evt.model_dump(mode="json"), ensure_ascii=False),
            event=err_evt.event,
        )
    else:
        done_evt = StreamEvent(
            event="done",
            thread_id=thread_id,
            data={
                "final_status": chunk.get("final_status"),
                "approved_diff": chunk.get("approved_diff"),
                "reviewer_decision": chunk.get("reviewer_decision"),
            },
            trace_id=trace_id,
        )
        yield ServerSentEvent(
            data=json.dumps(done_evt.model_dump(mode="json"), ensure_ascii=False),
            event=done_evt.event,
        )

    # 等 SENTINEL 确保 executor 已交差(便于 finally 释放 slot)
    await queue.get()


@router.post("/code-mod", summary="代码修改 + Maker/Checker 子图 SSE 流")
async def post_code_mod(
    thread_id: str,
    body: dict[str, Any],
    request: Request,
    trace_id: str = Depends(get_trace_id),
    audit: AuditLogger = Depends(get_audit),
) -> EventSourceResponse:
    """接收 user 修改请求,推动 coder_review_subgraph,SSE 流式返回结果。

    Args:
        thread_id: thread 主键(path param)。
        body: ``{"request": <str required>, "skill_names": [...]}``。
        request: FastAPI 请求对象。
        trace_id: 来自 DI 的 trace_id(header 或生成)。
        audit: 来自 DI 的 AuditLogger。

    Returns:
        ``EventSourceResponse``,``text/event-stream``,包含 ``done`` event。

    Raises:
        ApiError: 422 ``validation_error``(缺 / 非字符串 request);
            409 ``thread_already_active``(同 thread 已有 in-flight 流)。
    """
    ev = _acquire_stream_slot(thread_id)
    request_obj = body.get("request")
    if not isinstance(request_obj, str) or not request_obj:
        # 释放 slot:validation 错误不能让流保持 active
        _release_stream_slot(thread_id, ev)
        raise ApiError(
            code="validation_error",
            message="'request' 字段必填且为非空字符串",
            status_code=422,
        )
    audit.emit(
        "api_post_code_mod",
        {
            "request_length": len(request_obj),
            "skill_names": body.get("skill_names", []),
            "trace_id": trace_id,
        },
        thread_id=thread_id,
    )
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    graph = _get_compiled_graph(request, thread_id)
    input_dict: CodeModState = {
        "request": request_obj,
        "thread_id": thread_id,
        "skill_names": body.get("skill_names", []),  # Phase 7 过滤用
    }

    async def _gen() -> AsyncIterator[ServerSentEvent]:
        try:
            async for evt in _stream_code_mod(
                graph, config, input_dict, thread_id, trace_id, audit,
            ):
                yield evt
        finally:
            _release_stream_slot(thread_id, ev)

    return EventSourceResponse(_gen(), ping=15)


__all__ = [
    "router",
    "post_code_mod",
    "_run_coder_review",  # test seam — 不要在生产代码里调用
    "_acquire_stream_slot",
    "_release_stream_slot",
    "_get_compiled_graph",
]
