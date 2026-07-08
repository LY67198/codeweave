from typing import get_type_hints
from codeweave.state.schemas import RootState, PlanState, ExecuteState


def test_root_state_has_messages():
    hints = get_type_hints(RootState)
    assert "messages" in hints
    assert "thread_id" in hints
    assert "plan_mode" in hints
    assert "next_agent" in hints


def test_plan_state_inherits_root():
    assert issubclass(PlanState, RootState)
    hints = get_type_hints(PlanState)
    assert "exploration_findings" in hints


def test_execute_state_inherits_root():
    assert issubclass(ExecuteState, RootState)
    hints = get_type_hints(ExecuteState)
    assert "code_diffs" in hints
    assert "review_iterations" in hints


def test_next_agent_literal_includes_all_agents():
    from typing import get_args
    hints = get_type_hints(RootState)
    next_agent_type = hints["next_agent"]
    values = get_args(next_agent_type)
    expected = {"supervisor", "explorer", "coder", "reviewer", "executor", "compact", "__end__"}
    assert expected.issubset(set(values))