"""Supervisor 单元测试(function calling 模式)。"""
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage
from langgraph.types import Command

from codeweave.agents.supervisor import supervisor_decision, supervisor_node


def test_supervisor_decision_tool_has_valid_args():
    """supervisor_decision 工具包含 next/reason 两个参数。"""
    # LangChain @tool 把函数包装成 StructuredTool,验证其 schema
    assert supervisor_decision.name == "supervisor_decision"
    schema = supervisor_decision.args_schema
    assert "next" in schema.model_fields
    assert "reason" in schema.model_fields


@patch("codeweave.agents.supervisor.get_chat_model")
def test_supervisor_node_returns_command(mock_get_model):
    """Supervisor 从 tool_call 提取决策,转为 Command。"""
    # mock LLM:bind_tools().invoke() 返回带 tool_calls 的 AIMessage
    mock_llm = MagicMock()
    mock_with_tools = MagicMock()
    mock_with_tools.invoke.return_value = AIMessage(
        content="",
        tool_calls=[{
            "name": "supervisor_decision",
            "args": {"next": "explorer", "reason": "explore first"},
            "id": "call_1",
        }],
    )
    mock_llm.bind_tools.return_value = mock_with_tools
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
    # agent_history 应当记录了这次决策
    assert result.update["agent_history"][-1]["decision"] == "explorer"
    assert result.update["agent_history"][-1]["reason"] == "explore first"


@patch("codeweave.agents.supervisor.get_chat_model")
def test_supervisor_node_handles_finish(mock_get_model):
    """决策为 FINISH 时 goto='__end__'。"""
    mock_llm = MagicMock()
    mock_with_tools = MagicMock()
    mock_with_tools.invoke.return_value = AIMessage(
        content="",
        tool_calls=[{
            "name": "supervisor_decision",
            "args": {"next": "FINISH", "reason": "task done"},
            "id": "call_1",
        }],
    )
    mock_llm.bind_tools.return_value = mock_with_tools
    mock_get_model.return_value = mock_llm

    result = supervisor_node({
        "messages": [AIMessage(content="test")],
        "todos": [],
        "plan_mode": False,
        "agent_history": [],
    })

    assert result.goto == "__end__"


@patch("codeweave.agents.supervisor.get_chat_model")
def test_supervisor_node_fallback_when_no_tool_call(mock_get_model):
    """LLM 没调工具时兜底到 FINISH(防止无限循环)。"""
    mock_llm = MagicMock()
    mock_with_tools = MagicMock()
    mock_with_tools.invoke.return_value = AIMessage(content="just text, no tool call")
    mock_llm.bind_tools.return_value = mock_with_tools
    mock_get_model.return_value = mock_llm

    result = supervisor_node({
        "messages": [AIMessage(content="test")],
        "todos": [],
        "plan_mode": False,
        "agent_history": [],
    })

    assert result.goto == "__end__"
    assert "fallback" in result.update["agent_history"][-1]["reason"]


@patch("codeweave.agents.supervisor.get_chat_model")
def test_supervisor_node_fallback_on_invalid_next(mock_get_model):
    """LLM 返回非法 next 值时兜底到 FINISH。"""
    mock_llm = MagicMock()
    mock_with_tools = MagicMock()
    mock_with_tools.invoke.return_value = AIMessage(
        content="",
        tool_calls=[{
            "name": "supervisor_decision",
            "args": {"next": "nonexistent_agent", "reason": "weird"},
            "id": "call_1",
        }],
    )
    mock_llm.bind_tools.return_value = mock_with_tools
    mock_get_model.return_value = mock_llm

    result = supervisor_node({
        "messages": [AIMessage(content="test")],
        "todos": [],
        "plan_mode": False,
        "agent_history": [],
    })

    assert result.goto == "__end__"
    assert "invalid" in result.update["agent_history"][-1]["reason"]
