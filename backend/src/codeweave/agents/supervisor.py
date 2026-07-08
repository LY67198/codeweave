"""Supervisor Agent —— 决策下一个要运行的 Agent。

使用 function calling(``bind_tools``)而非 ``with_structured_output``,
原因是 DeepSeek 等 OpenAI 兼容服务不支持 ``json_schema`` response_format,
但都支持 function calling(更早且更通用的协议)。
"""
from typing import Literal

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.types import Command

from codeweave.config.model import get_chat_model
from codeweave.state.schemas import RootState


SUPERVISOR_PROMPT = """You are a supervisor orchestrating coding agents.

Available agents (重要:谁有工具 vs 谁只是占位):
- executor: **唯一有工具的 agent**(read_file / write_file / edit_file / grep_files / run_bash / todo_write)
  - 凡是涉及"读/写/编辑/搜索/跑命令"的任务,都必须路由到这里
  - 用户提到"用 read_file"、"调工具"、"跑测试"等 → 选 executor
- explorer: 描述代码库(Phase 1 占位,无工具,执行后返回空)→ 不要路由到这里
- coder: 写/改代码(Phase 1 占位)
- reviewer: 评审变更(Phase 1 占位)
- compact: 压缩上下文(Phase 3 占位)
- FINISH: 任务完成

注意:除非用户明确表示任务已完成,否则应选 executor(它有工具可以真正做事)。

Current todos: {todos}
Last agent: {last_agent}
Plan mode: {plan_mode}

Decide the next agent. Be decisive. Call the supervisor_decision tool with your choice.
"""


# 合法 next 取值(用于 validation 兜底)
_VALID_NEXT = (
    "supervisor", "explorer", "coder", "reviewer", "executor", "compact", "FINISH",
)


@tool
def supervisor_decision(
    next: Literal[
        "supervisor", "explorer", "coder", "reviewer", "executor", "compact", "FINISH",
    ],
    reason: str = "",
) -> str:
    """Decide the next agent to call. Call this with your choice.

    Args:
        next: Name of the next agent to run, or ``"FINISH"`` to end the run.
        reason: Brief reason for this decision (1-2 sentences).

    Returns:
        确认字符串(LLM 看到即可,实际不消费返回值)。
    """
    return f"Decision: next={next}, reason={reason}"


def supervisor_node(state: RootState) -> Command[Literal["supervisor", "explorer", "coder", "reviewer", "executor", "compact", "__end__"]]:
    """根据当前 state 决策下一个要运行的 Agent。

    通过 ``bind_tools`` 让 LLM 以 function calling 形式返回结构化决策,
    再从 ``tool_calls[0]`` 提取 ``next`` 和 ``reason``。

    Args:
        state: 当前 graph state,包含 messages、todos、plan_mode、
            agent_history 等字段。

    Returns:
        LangGraph ``Command`` 对象,包含 state 更新(追加到 ``agent_history``)
        和下一个节点的 ``goto`` 目标(若决策为 ``FINISH`` 则 ``goto="__end__``)。
    """
    llm = get_chat_model()
    llm_with_tools = llm.bind_tools([supervisor_decision])

    last_agent = ""
    if state.get("agent_history"):
        last_agent = state["agent_history"][-1].get("name", "")

    prompt = SUPERVISOR_PROMPT.format(
        todos=state.get("todos", []),
        last_agent=last_agent,
        plan_mode=state.get("plan_mode", False),
    )

    response = llm_with_tools.invoke([
        SystemMessage(content=prompt),
        *state.get("messages", [])[-5:],
    ])

    # 兜底:LLM 没调工具 → FINISH(防止无限循环)
    if not response.tool_calls:
        return Command(
            update={"agent_history": [
                {"name": "supervisor", "decision": "FINISH",
                 "reason": "no tool call, fallback"},
            ]},
            goto="__end__",
        )

    tool_call = response.tool_calls[0]
    args = tool_call.get("args", {})
    next_agent_name = args.get("next", "FINISH")
    reason = args.get("reason", "")

    # 兜底:LLM 返回了非法 next 值 → FINISH
    if next_agent_name not in _VALID_NEXT:
        next_agent_name = "FINISH"
        reason = f"invalid next value {next_agent_name!r}, fallback to FINISH"

    next_node = next_agent_name if next_agent_name != "FINISH" else "__end__"

    return Command(
        update={"agent_history": [
            {"name": "supervisor", "decision": next_agent_name, "reason": reason},
        ]},
        goto=next_node,
    )
