from typing import Annotated, Literal, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class Todo(TypedDict):
    id: str
    content: str
    status: Literal["pending", "in_progress", "completed"]
    activeform: str


class RootState(TypedDict, total=False):
    """Plan 和 Execute Subgraph 共享的状态。"""
    # === 消息（LangGraph 内置 Reducer）===
    messages: Annotated[list[BaseMessage], add_messages]

    # === 任务元信息 ===
    thread_id: str
    user_request: str
    session_started_at: str

    # === 计划 ===
    plan: list[dict] | None
    plan_decision: Literal["approve", "edit", "reject"] | None
    plan_feedback: str | None

    # === 待办 ===
    todos: list[Todo]

    # === 上下文管理 ===
    token_count: int
    compact_threshold: int
    compact_count: int
    last_compact_summary: str | None

    # === 路由 ===
    next_agent: Literal[
        "supervisor", "explorer", "coder",
        "reviewer", "executor", "compact", "__end__"
    ]
    plan_mode: bool
    recursion_remaining: int

    # === 子 Agent 并行（Send）===
    parallel_tasks: list[dict] | None

    # === 审计 ===
    agent_history: list[dict]


class PlanState(RootState):
    """Plan Subgraph 特有的状态。"""
    exploration_findings: list[str]
    proposed_steps: list[dict]
    approval_pending: bool


class ExecuteState(RootState):
    """Execute Subgraph 特有的状态。"""
    code_diffs: list[dict]
    review_iterations: int
    last_review_feedback: list[str]
    test_results: list[dict]
