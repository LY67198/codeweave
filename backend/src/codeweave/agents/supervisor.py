from typing import Literal

from langchain_core.messages import SystemMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from codeweave.config.model import get_chat_model
from codeweave.state.schemas import RootState


SUPERVISOR_PROMPT = """You are a supervisor orchestrating coding agents.

Available agents:
- explorer: explore codebase (read-only)
- coder: write/edit code
- reviewer: review code changes
- executor: run tests
- compact: compress context
- FINISH: task complete

Current todos: {todos}
Last agent: {last_agent}
Plan mode: {plan_mode}

Decide the next agent. Be decisive.
"""


class SupervisorDecision(BaseModel):
    """来自 Supervisor 的结构化决策结果。

    Attributes:
        next: 下一个要运行的 Agent 名称,或 ``FINISH`` 表示任务结束。
        reason: 决策的简短理由,默认为空字符串。
    """
    next: Literal["supervisor", "explorer", "coder", "reviewer", "executor", "compact", "FINISH"]
    reason: str = Field(default="")


def supervisor_node(state: RootState) -> Command:
    """根据当前 state 决策下一个要运行的 Agent。

    使用 LangChain 的 ``with_structured_output`` 让 LLM 返回强类型
    ``SupervisorDecision``,然后通过 ``Command(update=..., goto=...)``
    同时完成 state 更新和路由。

    Args:
        state: 当前 graph state,包含 messages、todos、plan_mode、
            agent_history 等字段。

    Returns:
        LangGraph ``Command`` 对象,包含 state 更新(追加到 ``agent_history``)
        和下一个节点的 ``goto`` 目标(若决策为 ``FINISH`` 则 ``goto="__end__"``)。
    """
    llm = get_chat_model()
    structured_llm = llm.with_structured_output(SupervisorDecision)

    last_agent = ""
    if state.get("agent_history"):
        last_agent = state["agent_history"][-1].get("name", "")

    prompt = SUPERVISOR_PROMPT.format(
        todos=state.get("todos", []),
        last_agent=last_agent,
        plan_mode=state.get("plan_mode", False),
    )

    decision: SupervisorDecision = structured_llm.invoke([
        SystemMessage(content=prompt),
        *state.get("messages", [])[-5:],
    ])

    next_agent = decision.next if decision.next != "FINISH" else "__end__"

    return Command(
        update={
            "agent_history": [{"name": "supervisor", "decision": decision.next}],
        },
        goto=next_agent,
    )