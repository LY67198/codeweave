from typing import get_type_hints
from codeweave.state.schemas import RootState, PlanState, ExecuteState


def test_root_state_has_messages():
    hints = get_type_hints(RootState)
    assert "messages" in hints
    assert "thread_id" in hints
    assert "plan_mode" in hints
    assert "next_agent" in hints


def test_plan_state_inherits_root():
    # TypedDict doesn't support issubclass; verify fields instead
    plan_hints = get_type_hints(PlanState)
    root_hints = get_type_hints(RootState)
    for key in root_hints:
        assert key in plan_hints, f"PlanState missing {key} from RootState"
    assert "exploration_findings" in plan_hints
    assert "proposed_steps" in plan_hints
    assert "approval_pending" in plan_hints


def test_execute_state_inherits_root():
    # TypedDict doesn't support issubclass; verify fields instead
    exec_hints = get_type_hints(ExecuteState)
    root_hints = get_type_hints(RootState)
    for key in root_hints:
        assert key in exec_hints, f"ExecuteState missing {key} from RootState"
    assert "code_diffs" in exec_hints
    assert "review_iterations" in exec_hints
    assert "last_review_feedback" in exec_hints
    assert "test_results" in exec_hints


def test_next_agent_literal_includes_all_agents():
    from typing import get_args
    hints = get_type_hints(RootState)
    next_agent_type = hints["next_agent"]
    values = get_args(next_agent_type)
    expected = {"supervisor", "explorer", "coder", "reviewer", "executor", "compact", "__end__"}
    assert expected.issubset(set(values))