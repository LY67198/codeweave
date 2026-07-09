"""POST /messages + /resume 路由(SSE)(spec §2.1 / §3.7)。

提供:
- ``POST /threads/{thread_id}/messages``: 推 user 输入,启动 graph,流式 SSE
  推送中间状态 / 节点结果 / done 标记;
- ``POST /threads/{thread_id}/resume``: HITL 决策回传,继续 graph(Task 8 完善语义)。

并发保护用进程内 ``_active_streams`` 注册表:同 thread 已有 in-flight
流就 409,避免 LangGraph checkpointer 的 race 条件。

HITL 防 replay 用 ``_LAST_INTERRUPT_IDS`` 进程内缓存:每次 ``_stream_graph``
观察到 ``hitl_requested`` event,记录 ``thread_id → interrupt_id``;
``/resume`` 时校验 body 的 interrupt_id 是否匹配,不匹配则 422。
"""
from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from typing import Any, AsyncIterator, Callable

from fastapi import APIRouter, Depends, Request
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from sse_starlette.event import ServerSentEvent
from sse_starlette.sse import EventSourceResponse

from codeweave.api.deps import get_audit, get_trace_id
from codeweave.api.errors import ApiError
from codeweave.api.models.threads import HumanMessageIn, ResumeIn, StreamEvent
from codeweave.api.sse import chunk_to_event
from codeweave.persistence.audit import AuditLogger


router = APIRouter(prefix="/threads/{thread_id}", tags=["messages"])


# 进程内 in-flight stream registry(thread_id → asyncio.Event)
# 简单 in-memory 实现,Phase 4 demo 够用;Phase 7 可换 Redis flag
_active_streams: dict[str, asyncio.Event] = {}


# 进程内最近一次 hitl_requested 事件 id(thread_id → interrupt_id)
# /resume 用此防 replay:body.interrupt_id 必须匹配,否则 422。
# Phase 4 demo 用 in-memory 缓存;Phase 7 可换 Redis。stream 完成后会 pop。
_LAST_INTERRUPT_IDS: dict[str, str] = {}


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
            message=f"thread {thread_id} 已有进行中的 SSE 流,等它结束再发新消息",
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


def _get_compiled_graph(
    request: Request, thread_id: str
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """从 ``app.state.graph_cache`` 取该 thread 的编译图(线程安全 LRU)。"""
    cache: OrderedDict[str, Any] = request.app.state.graph_cache
    if thread_id not in cache:
        # Phase 4 / Phase 3 的 execute_graph 拓扑不变,跨 thread 复用同一编译图。
        # LRU cache 避免每次请求重建;checkpointer / store 由 lifespan 持有。
        cache[thread_id] = (
            __import__(
                "codeweave.graphs.execute_graph",
                fromlist=["build_execute_graph"],
            )
            .build_execute_graph()
            .compile(
                checkpointer=request.app.state.checkpointer,
                store=request.app.state.store,
            )
        )
    else:
        # LRU touch
        cache.move_to_end(thread_id)
    return cache[thread_id]  # type: ignore[no-any-return]


async def _stream_graph(
    graph: CompiledStateGraph[Any, Any, Any, Any],
    config: RunnableConfig,
    input_dict: dict[str, Any] | Command[Any],
    audit: AuditLogger,
    trace_id: str,
    thread_id: str,
    on_complete: Callable[[], None] | None = None,
) -> AsyncIterator[ServerSentEvent]:
    """把同步 ``graph.stream`` 包装成异步 SSE 事件流(§3.6)。

    内部用 ``asyncio.Queue`` 在 thread ↔ coroutine 间传 chunk;
    使用 uvicorn 的 default ThreadPoolExecutor 跑同步 generator。

    Args:
        graph: 编译好的 LangGraph 图。
        config: LangGraph ``configurable.thread_id`` 配置。
        input_dict: 推入 graph 的初始 state 或 ``Command``(resume / goto)。
        audit: AuditLogger,中间转换错误会写 audit。
        trace_id: 贯穿请求追踪 id。
        thread_id: 当前 thread 主键(写进每个 event 上下文)。
        on_complete: stream 自然结束后回调(用于清理 ``_LAST_INTERRUPT_IDS``)。

    Yields:
        ``ServerSentEvent`` 对象(交给 sse-starlette 序列化,而不是预格式化字符串,
        否则 sse-starlette 会把整个字符串当成 ``data:`` 字段再次包裹)。
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=64)
    SENTINEL = object()

    def _run_sync() -> None:
        try:
            for chunk in graph.stream(
                input_dict, config=config, stream_mode="updates"
            ):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, SENTINEL)

    # 跑在 default executor(uvicorn reuse)
    loop.run_in_executor(None, _run_sync)

    while True:
        chunk = await queue.get()
        if chunk is SENTINEL:
            break
        try:
            # chunk_to_event 已支持 LangGraph dict-shape + tuple-shape + interrupt chunk
            evt = chunk_to_event(chunk, thread_id=thread_id, trace_id=trace_id)
            # 记下 interrupt_id 给 /resume 防 replay 用
            if evt.event == "hitl_requested":
                _LAST_INTERRUPT_IDS[thread_id] = evt.data.get("interrupt_id", "")
        except Exception as exc:
            audit.emit(
                "api_sse_translate_error",
                {"error": str(exc), "chunk_type": type(chunk).__name__},
                thread_id=thread_id,
            )
            continue
        yield ServerSentEvent(
            data=json.dumps(evt.model_dump(mode="json"), ensure_ascii=False),
            event=evt.event,
        )

    # stream 自然结束,先清 replay guard(若有),再发 done
    if on_complete is not None:
        on_complete()

    # 末尾发 done 事件
    done_evt = StreamEvent(
        event="done",
        thread_id=thread_id,
        data={"trace_id": trace_id},
        trace_id=trace_id,
    )
    yield ServerSentEvent(
        data=json.dumps(done_evt.model_dump(mode="json"), ensure_ascii=False),
        event=done_evt.event,
    )


@router.post("/messages", summary="推 user 输入,启动 graph 并 SSE 输出")
async def post_message(
    thread_id: str,
    body: HumanMessageIn,
    request: Request,
    trace_id: str = Depends(get_trace_id),
    audit: AuditLogger = Depends(get_audit),
) -> EventSourceResponse:
    """把 user content 推入 graph,流式返回中间事件。

    并发保护:同 thread 已有 in-flight 流时 409。

    Args:
        thread_id: thread 主键(path param)。
        body: 包含 ``content`` 的 ``HumanMessageIn``。
        request: FastAPI request,用于 DI cache 读取。
        trace_id: 来自 DI 的 trace_id(优先取 header,否则生成)。
        audit: 来自 DI 的 AuditLogger。

    Returns:
        ``EventSourceResponse``,``text/event-stream``。
    """
    ev = _acquire_stream_slot(thread_id)
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    graph = _get_compiled_graph(request, thread_id)
    audit.emit(
        "api_post_message",
        {"content_length": len(body.content), "trace_id": trace_id},
        thread_id=thread_id,
    )

    async def _gen() -> AsyncIterator[ServerSentEvent]:
        try:
            async for chunk in _stream_graph(
                graph,
                config,
                {"messages": [HumanMessage(content=body.content)]},
                audit=audit,
                trace_id=trace_id,
                thread_id=thread_id,
            ):
                yield chunk
        finally:
            _release_stream_slot(thread_id, ev)

    return EventSourceResponse(_gen(), ping=15)


@router.post("/resume", summary="HITL 决策回传,继续 graph")
async def post_resume(
    thread_id: str,
    body: ResumeIn,
    request: Request,
    trace_id: str = Depends(get_trace_id),
    audit: AuditLogger = Depends(get_audit),
) -> EventSourceResponse:
    """HITL 决策继续。``interrupt_id`` 必须匹配上次 ``hitl_requested`` event。

    实现细节:
    1. 读 ``_LAST_INTERRUPT_IDS.get(thread_id)``,若与 ``body.interrupt_id``
       不一致则 422 ``interrupt_id_mismatch``(防 replay);
    2. 用 ``Command(resume=body.decision)`` 推进 graph;
    3. stream 自然结束后,``on_complete`` 回调清掉 ``_LAST_INTERRUPT_IDS``。

    Args:
        thread_id: thread 主键(path param)。
        body: ``ResumeIn`` 包含 ``interrupt_id`` + ``decision``。
        request: FastAPI request。
        trace_id: 来自 DI 的 trace_id。
        audit: 来自 DI 的 AuditLogger。

    Returns:
        ``EventSourceResponse``,``text/event-stream``。

    Raises:
        ApiError: interrupt_id 不匹配时 422。
    """
    ev = _acquire_stream_slot(thread_id)
    last_interrupt_id = _LAST_INTERRUPT_IDS.get(thread_id)
    if last_interrupt_id and body.interrupt_id != last_interrupt_id:
        audit.emit(
            "api_resume_interrupt_mismatch",
            {
                "expected": last_interrupt_id,
                "received": body.interrupt_id,
                "trace_id": trace_id,
            },
            thread_id=thread_id,
        )
        raise ApiError(
            code="interrupt_id_mismatch",
            message=(
                f"interrupt_id 不匹配:期望 {last_interrupt_id},"
                f"收到 {body.interrupt_id}"
            ),
            status_code=422,
        )

    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    graph = _get_compiled_graph(request, thread_id)
    audit.emit(
        "api_post_resume",
        {
            "interrupt_id": body.interrupt_id,
            "decision": body.decision,
            "trace_id": trace_id,
        },
        thread_id=thread_id,
    )

    def _clear_last_interrupt() -> None:
        """stream 自然结束后清掉该 thread 的 last interrupt id。"""
        _LAST_INTERRUPT_IDS.pop(thread_id, None)

    async def _gen() -> AsyncIterator[ServerSentEvent]:
        try:
            async for chunk in _stream_graph(
                graph,
                config,
                Command(resume=body.decision),
                audit=audit,
                trace_id=trace_id,
                thread_id=thread_id,
                on_complete=_clear_last_interrupt,
            ):
                yield chunk
        finally:
            _release_stream_slot(thread_id, ev)

    return EventSourceResponse(_gen(), ping=15)