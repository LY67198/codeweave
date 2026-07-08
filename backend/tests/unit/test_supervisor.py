from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, SystemMessage
from codeweave.agents.supervisor import SupervisorDecision, supervisor_node


def test_supervisor_decision_typed():
    """SupervisorDecision has expected fields."""
    d = SupervisorDecision(next="coder", reason="need to write code")
    assert d.next == "coder"
    assert d.reason == "need to write code"


@patch("codeweave.agents.supervisor.get_chat_model")
def test_supervisor_node_returns_command(mock_get_model):
    """Supervisor returns Command with update + goto."""
    from langgraph.types import Command

    # Mock LLM with structured output
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = SupervisorDecision(next="explorer", reason="explore first")
    mock_llm.with_structured_output.return_value = mock_structured
    mock_get_model.return_value = mock_llm

    state = {
        "messages": [AIMessage(content="test")],
        "todos": [],
        "plan_mode": False,
        "agent_history": [],
    }

    result = supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "explorer"