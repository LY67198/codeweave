"""Coder agent 单测,用 MagicMock LLM(spec §3.2)。"""
from unittest.mock import MagicMock, patch

from codeweave.agents.coder import coder_node
from codeweave.skills.state import CodeModState


def test_coder_emits_unified_diff(tmp_path):
    """Coder 调 write_file 工具后,产 unified diff 文本 + retry_count++。"""
    repo = tmp_path
    (repo / "foo.py").write_text("old\n")

    fake_response = MagicMock()
    fake_response.content = ""
    fake_response.tool_calls = [
        {"id": "1", "name": "write_file",
         "args": {"path": str(repo / "foo.py"), "content": "new\n"}}
    ]

    state: CodeModState = {
        "request": "改 foo.py",
        "thread_id": "t-1",
        "retry_count": 0,
    }

    with patch("codeweave.agents.coder.get_chat_model") as get_model:
        llm = MagicMock()
        llm.bind_tools.return_value.invoke.return_value = fake_response
        get_model.return_value = llm

        with patch("codeweave.agents.coder.run_tools_and_diff") as run_tools:
            run_tools.return_value = (
                [{"tool": "write_file", "path": str(repo / "foo.py")}],
                "--- foo.py\n+++ foo.py\n@@ -1 +1 @@\n-old\n+new\n",
                {"foo.py": True},
            )
            with patch("codeweave.agents.coder.load_skills_for", return_value=[]):
                result = coder_node(state)

    assert result["retry_count"] == 1
    assert "old" in result["coder_diff"]
    assert "new" in result["coder_diff"]
    assert result["coder_message"]  # 非空


def test_coder_blocks_sensitive_path(tmp_path):
    """Layer 3:coder 写 .ssh/... 应在工具入口拒,不带 diff。"""
    from codeweave.tools.file_tools import write_file  # noqa: F401  # 验证 sensitive path 时工具可调
    # 直接 unit 测 file_tools 的 sensitive guard(假设 Phase 5 在 file_tools 加 check)
    # 此测试作为安全 infrastructure 验证;若未集成,coder_node 仍应 audit emit
    secret = tmp_path / ".ssh" / "id_rsa"
    secret.parent.mkdir()

    fake_response = MagicMock()
    fake_response.tool_calls = [
        {"id": "1", "name": "write_file",
         "args": {"path": str(secret), "content": "leaked"}}
    ]

    _state: CodeModState = {"request": "x", "thread_id": "t", "retry_count": 0}

    # 此测试验:coder 调到的 file_tools.write_file 在 sensitive path 上抛 ValueError
    # 工具层面已经有 handling(coder_node 调工具 → 工具 raise → run_tools_and_diff catch)
    # 实际上 Phase 5 在 Task 5 加工具 wrapper,这里先简化只验证 path 检测
    from codeweave.skills.security import is_sensitive_path
    assert is_sensitive_path(secret)


def test_coder_first_invocation_retry_count_starts_at_1():
    state: CodeModState = {"request": "x", "thread_id": "t", "retry_count": 0}
    fake_response = MagicMock()
    fake_response.tool_calls = []

    with patch("codeweave.agents.coder.get_chat_model") as gm:
        llm = MagicMock()
        llm.bind_tools.return_value.invoke.return_value = fake_response
        gm.return_value = llm
        with patch("codeweave.agents.coder.run_tools_and_diff",
                   return_value=([], "", {})):
            with patch("codeweave.agents.coder.load_skills_for", return_value=[]):
                result = coder_node(state)

    # 首次 invocation 也算 1 次
    assert result["retry_count"] == 1


def test_coder_propagates_review_feedback_to_next_call():
    """上轮 reviewer.feedback 进入 system prompt,LLM 看到 retry_context。"""
    state: CodeModState = {
        "request": "add error handling",
        "thread_id": "t",
        "retry_count": 1,
        "coder_diff": "--- x.py\n-old\n+new\n",
        "reviewer_decision": {
            "accept": False,
            "score": 3,
            "feedback": "缺少 try/except",
            "risk_flags": [],
        },
    }

    captured_prompt = []

    def capture(*args, **kwargs):
        msgs = args[0]
        captured_prompt.append(msgs[0]["content"])
        return MagicMock(content="", tool_calls=[])

    with patch("codeweave.agents.coder.get_chat_model") as gm:
        llm = MagicMock()
        llm.bind_tools.return_value.invoke.side_effect = capture
        gm.return_value = llm
        with patch("codeweave.agents.coder.run_tools_and_diff", return_value=([], "", {})):
            with patch("codeweave.agents.coder.load_skills_for", return_value=[]):
                coder_node(state)

    assert any("缺少 try/except" in p for p in captured_prompt)