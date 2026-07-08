"""todo_write 工具:更新 in-progress 的待办列表。

注意:工具不直接修改 state.todos,它只返回过滤后的 todo 列表。
由 Agent 节点(executor)拿到 ToolMessage 后,用 Command(update={"todos": ...}) 写回 state。
state.todos 字段用 ``merge_todos`` reducer 做最终合并。

Phase 3 (Task 10) 起,每个工具调用结束后会通过模块级 ``_audit`` 全局变量
emit ``tool_call`` audit 事件(若 ``_audit`` 为 ``None`` 则跳过,工具仍正常工作)。
"""
from __future__ import annotations

import time
from typing import Annotated, Any

from langchain_core.tools import ToolException

from codeweave.persistence.audit import AuditLogger
from codeweave.tools.registry import register


# 合法的 status 取值
_VALID_STATUSES = frozenset({"pending", "in_progress", "completed"})
# todo 字典必须包含的字段
_REQUIRED_FIELDS = ("id", "content", "status", "activeform")


# ---------------------------------------------------------------------------
# Audit 集成(Phase 3 Task 10)
# ---------------------------------------------------------------------------

# 模块级 AuditLogger 句柄。默认 None,表示无 audit;测试 / graph 启动后可注入。
_audit: AuditLogger | None = None


def set_audit_logger(logger: AuditLogger | None) -> None:
    """注入 / 清除模块级 AuditLogger。

    Args:
        logger: AuditLogger 实例,或 None。
    """
    global _audit
    _audit = logger


def _emit_tool_call(
    tool_name: str,
    args: dict[str, Any],
    result: Any,
    duration_ms: int,
    thread_id: str,
) -> None:
    """emit ``tool_call`` audit 事件。失败吞掉异常,业务继续。

    Args:
        tool_name: 工具名(用于 payload.tool)。
        args: 工具调用参数(用于 payload.args)。
        result: 工具返回值(截断到 200 字符写入 payload.result_summary)。
        duration_ms: 调用耗时(毫秒)。
        thread_id: 关联的 LangGraph thread_id,缺省 ``"<no-thread>"``。
    """
    if _audit is None:
        return
    try:
        result_summary = repr(result)[:200]
        _audit.emit(
            "tool_call",
            {"tool": tool_name, "args": args, "result_summary": result_summary},
            thread_id=thread_id,
            duration_ms=duration_ms,
        )
    except Exception:  # noqa: BLE001
        # audit 失败不影响工具返回值(spec §5.3)
        pass


@register(name="todo_write", plan_mode_safe=False, requires_permission=False, category="todo")
def todo_write(
    todos: Annotated[list[dict[str, Any]], "完整 todo 列表(将替换当前 todos)"],
    thread_id: Annotated[str, "LangGraph thread_id(审计用)"] = "<no-thread>",
) -> list[dict[str, Any]]:
    """更新 todo 列表。已完成(status=completed)的项会被过滤掉。

    Args:
        todos: 完整 todo 列表,每项必须包含 id/content/status/activeform 四个字段。
        thread_id: LangGraph thread_id,用于 audit 关联,默认 ``"<no-thread>"``。

    Returns:
        过滤掉 completed 项后的 todo 列表(将作为 ToolMessage 返回给 LLM/Agent 节点)。

    Raises:
        ToolException: 字段缺失或 status 取值非法。
    """
    start = time.monotonic()
    validated: list[dict[str, Any]] = []
    for i, t in enumerate(todos):
        if not isinstance(t, dict):
            raise ToolException(f"todos[{i}] 不是 dict: {type(t).__name__}")
        missing = [f for f in _REQUIRED_FIELDS if f not in t]
        if missing:
            raise ToolException(f"todos[{i}] 缺少字段: {missing}")
        if t["status"] not in _VALID_STATUSES:
            raise ToolException(
                f"todos[{i}].status 非法: {t['status']!r}(必须是 pending/in_progress/completed)"
            )
        # 已完成的项不进入 state
        if t["status"] == "completed":
            continue
        validated.append(t)
    result = validated
    _emit_tool_call(
        "todo_write",
        {"todo_count": len(result), "input_count": len(todos)},
        result,
        int((time.monotonic() - start) * 1000),
        thread_id,
    )
    return result