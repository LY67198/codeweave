from typing import Annotated, Literal, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class Todo(TypedDict):
    id: str
    content: str
    status: Literal["pending", "in_progress", "completed"]
    activeform: str


class RootState(TypedDict, total=False):
    """Shared state for both Plan and Execute Subgraphs."""
    # === Messages (LangGraph built-in reducer) ===
    messages: Annotated[list[BaseMessage], add_messages]

    # === Task meta ===
    thread_id: str
    user_request: str
    session_started_at: str

    # === Plan ===
    plan: list[dict] | None
    plan_decision: Literal["approve", "edit", "reject"] | None
    plan_feedback: str | None

    # === Todo ===
    todos: list[Todo]

    # === Context management ===
    token_count: int
    compact_threshold: int
    compact_count: int
    last_compact_summary: str | None

    # === Routing ===
    next_agent: Literal[
        "supervisor", "explorer", "coder",
        "reviewer", "executor", "compact", "__end__"
    ]
    plan_mode: bool
    recursion_remaining: int

    # === Sub-agent parallel (Send) ===
    parallel_tasks: list[dict] | None

    # === Audit ===
    agent_history: list[dict]


class PlanState(RootState):
    """Plan Subgraph specific state."""
    exploration_findings: list[str]
    proposed_steps: list[dict]
    approval_pending: bool


class ExecuteState(RootState):
    """Execute Subgraph specific state."""
    code_diffs: list[dict]
    review_iterations: int
    last_review_feedback: list[str]
    test_results: list[dict]