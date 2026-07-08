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
    """来自 Supervisor 的结构化决策结果。"""
    next: Literal["supervisor", "explorer", "coder", "reviewer", "executor", "compact", "FINISH"]
    reason: str = Field(default="")


def supervisor_node(state: RootState) -> Command:
    """根据当前状态决策下一个运行的 Agent。"""
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