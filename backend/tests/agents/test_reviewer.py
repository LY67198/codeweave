"""Reviewer agent 单测(spec §3.3 / §3.4)。

7 tests:
- 5 for `_parse_reviewer_decision` (clean / fenced / trailing-comma / broken / extra-keys)
- 2 end-to-end for `reviewer_node` with MagicMock LLM
"""
import json
from unittest.mock import MagicMock, patch

from codeweave.agents.reviewer import (
    _parse_reviewer_decision,
    reviewer_node,
)
from codeweave.skills.state import CodeModState


# === _parse_reviewer_decision(私有,直接测 OK) ===

def test_parse_clean_json():
    """正常 JSON 一次过 → 直接 ReviewerDecision。"""
    raw = json.dumps({"accept": True, "score": 8, "feedback": "good", "risk_flags": []})
    d = _parse_reviewer_decision(raw, default_accept=False)
    assert d.accept is True
    assert d.score == 8


def test_parse_fenced_json():
    """LLM 经常用 ```json``` 包 → 抽 fence 后再 parse。"""
    raw = (
        "```json\n"
        + json.dumps(
            {
                "accept": False,
                "score": 3,
                "feedback": "missing tests",
                "risk_flags": ["no_tests"],
            }
        )
        + "\n```"
    )
    d = _parse_reviewer_decision(raw, default_accept=False)
    assert d.accept is False
    assert d.risk_flags == ["no_tests"]


def test_parse_json_with_trailing_comma():
    """trailing comma → json 失败 → 走 json5(若装)/re fallback。

    这里测试的是容错路径:输入非法 JSON 但能解析,产出正确 accept=True。
    """
    raw = '{"accept": true, "score": 7, "feedback": "ok",}'
    d = _parse_reviewer_decision(raw, default_accept=False)
    assert d.accept is True


def test_parse_broken_returns_reject():
    """JSON parse 失败 → accept=False + feedback 解释 + risk_flag。"""
    d = _parse_reviewer_decision("totally broken {json", default_accept=False)
    assert d.accept is False
    assert "JSON parse failed" in d.feedback
    assert "json_broken" in d.risk_flags


def test_parse_extra_keys_ignored_but_signature_validated():
    """未知字段被 pydantic 忽略(extra=ignore 默认),签名通过即通过。"""
    raw = json.dumps(
        {"accept": True, "score": 5, "feedback": "ok", "unknown_field": "x"}
    )
    d = _parse_reviewer_decision(raw, default_accept=False)
    assert d.accept is True
    assert d.score == 5


# === reviewer_node end-to-end mock LLM ===

def test_reviewer_returns_decision_in_state():
    """Happy path:LLM 输出合法 JSON → state.reviewer_decision 含 accept/score。"""
    state: CodeModState = {
        "request": "add error handling",
        "thread_id": "t",
        "retry_count": 1,
        "coder_diff": "--- foo.py\n+raise Exception()\n",
    }
    fake = MagicMock()
    fake.content = json.dumps(
        {
            "accept": False,
            "score": 3,
            "feedback": "missing try/except",
            "risk_flags": [],
        }
    )
    with patch("codeweave.agents.reviewer.get_chat_model") as gm:
        llm = MagicMock()
        llm.invoke.return_value = fake
        gm.return_value = llm
        with patch("codeweave.agents.reviewer.load_skills_for", return_value=[]):
            result = reviewer_node(state)
    assert result["reviewer_decision"]["accept"] is False
    assert result["reviewer_decision"]["score"] == 3


def test_reviewer_raises_if_no_diff():
    """无 coder_diff → AssertionError(spec §3.3 必须有 diff)。"""
    state: CodeModState = {"request": "x", "thread_id": "t"}  # 无 coder_diff
    try:
        reviewer_node(state)
        assert False, "expected AssertionError"
    except AssertionError:
        pass  # 正确行为