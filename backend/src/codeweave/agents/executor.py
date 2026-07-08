"""Executor Agent —— 标准 ReAct 双节点(executor ⇄ tools)。

Reasoning(executor_node) + Acting(tools_node) 分离,符合 LangGraph 推荐的
ToolNode 模式:executor 调 LLM,tools 跑 ToolNode,循环直至 LLM 不再调工具。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from codeweave.config.model import get_chat_model
from codeweave.state.reducers import merge_todos
from codeweave.state.schemas import RootState
from codeweave.tools import get_tools_for_mode


@lru_cache(maxsize=1)
def _get_executor_model() -> Any:
    """惰性初始化绑定工具的 LLM(避免模块加载时硬性依赖 langchain-openai)。"""
    return get_chat_model().bind_tools(get_tools_for_mode("execute"))


@lru_cache(maxsize=1)
def _get_executor_tool_node() -> ToolNode:
    """惰性初始化 ToolNode。"""
    return ToolNode(get_tools_for_mode("execute"))


def executor_node(state: RootState) -> Command[Literal["tools", "__end__"]]:
    """ReAct 的 Reasoning 步骤:调 LLM,根据 tool_calls 决定路由。

    路由:
        - LLM 返回 tool_calls → ``"tools"`` 节点(执行工具)
        - LLM 不调工具(纯文本回答)→ ``"__end__"`` 结束本轮

    Args:
        state: 当前 graph state,至少包含 ``messages``。

    Returns:
        ``Command`` 对象,追加 AIMessage 到 messages,``goto`` 指明下一步。
    """
    model = _get_executor_model()
    messages: list[BaseMessage] = list(state.get("messages") or [])
    response: AIMessage = model.invoke(messages)
    messages.append(response)

    if not response.tool_calls:
        return Command(update={"messages": messages}, goto="__end__")

    return Command(update={"messages": messages}, goto="tools")


def executor_tools_node(state: RootState) -> Command[Literal["executor"]]:
    """ReAct 的 Acting + Observing 步骤:执行 tool_call,合并 todo,回 executor。

    流程:
        1. 取最后一条 AIMessage(带 tool_calls)
        2. 用 ToolNode 执行所有 tool_call,得到 ToolMessage 列表
        3. 若 todo_write 被调用,合并其返回值到 state.todos
        4. 路由回 ``"executor"`` 让 LLM 继续 Reasoning

    Args:
        state: 当前 graph state,最后一条消息应是带 tool_calls 的 AIMessage。

    Returns:
        ``Command`` 对象,追加 ToolMessages 到 messages,可含 todos 更新,``goto="executor"``。
    """
    tool_node = _get_executor_tool_node()

    messages: list[BaseMessage] = list(state.get("messages") or [])
    last_ai = messages[-1]  # AIMessage with tool_calls

    tool_result = tool_node.invoke({"messages": [last_ai]})
    new_messages: list[BaseMessage] = tool_result["messages"]
    messages.extend(new_messages)

    # 合并 todo_write 返回到 state.todos
    todos_update: list[dict[str, Any]] = []
    for msg in new_messages:
        if hasattr(msg, "name") and getattr(msg, "name", "") == "todo_write":
            content = msg.content
            if isinstance(content, list):
                todos_update = cast(list[dict[str, Any]], content)

    # 实验:不返回 messages update,只返回 todos(若有)
    update: dict[str, Any] = {"messages": new_messages}
    if todos_update:
        existing = list(state.get("todos") or [])
        existing_dicts = cast(list[dict[str, Any]], existing)
        update["todos"] = merge_todos(existing_dicts, todos_update)

    return Command(update=update, goto="executor")
