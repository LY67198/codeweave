"""Executor Agent —— 执行工具调用(读/写/编辑/grep/bash/todo)。

实际实现:绑定 6 个 execute 模式工具到 LLM,ToolNode 调度,
todo_write 的返回值通过 ``merge_todos`` reducer 合并到 state.todos。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from codeweave.config.model import get_chat_model
from codeweave.state.reducers import merge_todos
from codeweave.state.schemas import RootState
from codeweave.tools import get_tools_for_mode


@lru_cache(maxsize=1)
def _get_executor_model():
    """惰性初始化绑定工具的 LLM(避免模块加载时硬性依赖 langchain-openai)。"""
    return get_chat_model().bind_tools(get_tools_for_mode("execute"))


@lru_cache(maxsize=1)
def _get_executor_tool_node():
    """惰性初始化 ToolNode。"""
    return ToolNode(get_tools_for_mode("execute"))


def executor_node(state: RootState) -> Command[Literal["executor", "__end__"]]:
    """执行 LLM 调用 + tool 调度。

    流程:
    1. 调 LLM(已 bind 全部 execute 模式工具)
    2. 如果返回 tool_calls → 调 ToolNode,然后回到本节点
    3. 解析 todo_write 的返回,合并到 state.todos
    4. 路由:无 tool_calls → __end__;否则循环到 executor_node

    Args:
        state: 当前 graph state,至少包含 ``messages``。

    Returns:
        ``Command`` 对象,包含 messages 与可选的 todos 更新,以及 goto 目标。
    """
    model = _get_executor_model()
    tool_node = _get_executor_tool_node()

    messages: list[BaseMessage] = list(state.get("messages", []))  # type: ignore[arg-type]
    response: AIMessage = model.invoke(messages)
    messages.append(response)

    if not response.tool_calls:
        return Command(update={"messages": messages}, goto="__end__")

    # 用 ToolNode 执行所有 tool_call
    tool_result = tool_node.invoke({"messages": [response]})
    new_messages: list[BaseMessage] = tool_result["messages"]  # type: ignore[assignment]
    messages.extend(new_messages)

    # 检查 todo_write 的返回,合并到 state.todos
    todos_update: list[dict] = []
    for msg in new_messages:
        # ToolMessage.content 是 str 或 list;todo_write 返回 list
        if hasattr(msg, "name") and getattr(msg, "name", "") == "todo_write":
            content = msg.content
            if isinstance(content, list):
                todos_update = content  # type: ignore[assignment]
    if todos_update:
        existing = list(state.get("todos", []))  # type: ignore[arg-type]
        merged = merge_todos(existing, todos_update)
        return Command(update={"messages": messages, "todos": merged}, goto="executor")

    return Command(update={"messages": messages}, goto="executor")
