"""todo_write 工具:更新 in-progress 的待办列表。

注意:工具不直接修改 state.todos,它只返回过滤后的 todo 列表。
由 Agent 节点(executor)拿到 ToolMessage 后,用 Command(update={"todos": ...}) 写回 state。
state.todos 字段用 ``merge_todos`` reducer 做最终合并。
"""
from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import ToolException

from codeweave.tools.registry import register


# 合法的 status 取值
_VALID_STATUSES = frozenset({"pending", "in_progress", "completed"})
# todo 字典必须包含的字段
_REQUIRED_FIELDS = ("id", "content", "status", "activeform")


@register(name="todo_write", plan_mode_safe=False, requires_permission=False, category="todo")
def todo_write(
    todos: Annotated[list[dict[str, Any]], "完整 todo 列表(将替换当前 todos)"],
) -> list[dict[str, Any]]:
    """更新 todo 列表。已完成(status=completed)的项会被过滤掉。

    Args:
        todos: 完整 todo 列表,每项必须包含 id/content/status/activeform 四个字段。

    Returns:
        过滤掉 completed 项后的 todo 列表(将作为 ToolMessage 返回给 LLM/Agent 节点)。

    Raises:
        ToolException: 字段缺失或 status 取值非法。
    """
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
    return validated