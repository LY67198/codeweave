from typing import Annotated, Literal, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class Todo(TypedDict):
    """任务待办条目。

    Attributes:
        id: 待办条目的唯一标识。
        content: 待办内容的文字描述。
        status: 当前的执行状态,取值 ``pending`` / ``in_progress`` / ``completed``。
        activeform: 进行中状态下显示的动作描述(如 "Exploring codebase")。
    """
    id: str
    content: str
    status: Literal["pending", "in_progress", "completed"]
    activeform: str


class RootState(TypedDict, total=False):
    """Plan 和 Execute Subgraph 共享的状态。

    Plan 与 Execute 两个子图都基于此状态扩展,以便在父图中共享基础字段。

    Attributes:
        messages: 对话消息历史,使用 LangGraph 内置的 ``add_messages`` Reducer。
        thread_id: 当前会话的线程标识,用于 checkpoint 检索。
        user_request: 用户原始请求文本。
        session_started_at: 会话开始时间(ISO 字符串)。
        plan: 计划步骤列表,可能为 None。
        plan_decision: 用户对计划的决策,取值 ``approve`` / ``edit`` / ``reject``。
        plan_feedback: 用户对计划的反馈意见,可能为 None。
        todos: 任务待办列表。
        token_count: 当前上下文的 token 数量。
        compact_threshold: 触发自动压缩的 token 阈值。
        compact_count: 已执行压缩的次数。
        last_compact_summary: 上一次压缩得到的摘要,可能为 None。
        compact_pending: 是否已 dispatch Celery compact 但尚未 apply。
        last_dispatched_compact_id: 上一条 dispatch 的 compact ID(UUID 字符串),可能为 None。
        next_agent: 下一个要运行的 Agent 名称。
        plan_mode: 是否处于 Plan Mode。
        recursion_remaining: LangGraph 递归剩余次数。
        parallel_tasks: 通过 Send 派发的并行子任务,可能为 None。
        agent_history: Agent 调度审计日志,使用 ``trim_agent_history`` Reducer 裁剪。
    """
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
    compact_pending: bool
    last_dispatched_compact_id: str | None

    # === 路由 ===
    next_agent: Literal[
        "supervisor", "explorer", "coder",
        "reviewer", "executor", "compact", "compact_check", "__end__"
    ]
    plan_mode: bool
    recursion_remaining: int

    # === 子 Agent 并行（Send）===
    parallel_tasks: list[dict] | None

    # === 审计 ===
    agent_history: list[dict]


class PlanState(RootState):
    """Plan Subgraph 特有的状态。

    在 ``RootState`` 的基础上扩展计划阶段所需的字段。

    Attributes:
        exploration_findings: Explorer Agent 收集到的代码库发现。
        proposed_steps: 提出的计划步骤。
        approval_pending: 是否正在等待用户对计划的批准。
    """
    exploration_findings: list[str]
    proposed_steps: list[dict]
    approval_pending: bool


class ExecuteState(RootState):
    """Execute Subgraph 特有的状态。

    在 ``RootState`` 的基础上扩展代码执行与评审所需的字段。

    Attributes:
        code_diffs: Coder 生成的代码变更(文件级 diff 列表)。
        review_iterations: Coder ↔ Reviewer 循环已迭代的次数。
        last_review_feedback: Reviewer 最近一次的反馈意见。
        test_results: Executor 运行的测试结果列表。
    """
    code_diffs: list[dict]
    review_iterations: int
    last_review_feedback: list[str]
    test_results: list[dict]