"""Compact 摘要算法纯函数测试(spec §4.4)。"""
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from codeweave.services.compact_logic import (
    choose_compact_range,
    messages_to_history_text,
    render_compact_prompt,
    estimate_messages_tokens,
)


def test_choose_compact_range_keeps_all_system_and_recent_six():
    msgs = [SystemMessage(content="sys")] + [
        HumanMessage(content=f"m{i}") for i in range(20)
    ] + [AIMessage(content=f"a{i}") for i in range(20)]

    keep_first, keep_last = choose_compact_range(msgs, keep_last_n=6)

    # system 全保
    assert keep_first == len([m for m in msgs if isinstance(m, SystemMessage)])
    # 最近 6 条全保
    assert msgs[keep_first:][:0] == []
    assert keep_last == len(msgs) - 6


def test_choose_compact_range_short_history_returns_zero_length():
    msgs = [SystemMessage(content="sys"),
            HumanMessage(content="hi"),
            AIMessage(content="hello")]
    keep_first, keep_last = choose_compact_range(msgs, keep_last_n=6)
    # 历史太短,中间无可压缩
    assert keep_first == keep_last == len(msgs)


def test_estimate_messages_tokens_returns_positive_int():
    msgs = [HumanMessage(content="hello world" * 100)]
    n = estimate_messages_tokens(msgs)
    assert isinstance(n, int)
    assert n > 0


def test_messages_to_history_text_serializes_in_order():
    msgs = [HumanMessage(content="u1"), AIMessage(content="a1")]
    text = messages_to_history_text(msgs)
    assert "u1" in text and "a1" in text
    assert text.index("u1") < text.index("a1")


def test_render_compact_prompt_returns_nonempty_string():
    out = render_compact_prompt(messages=[HumanMessage(content="build a thing")],
                                keep_last_n=2,
                                max_summary_tokens=300)
    assert isinstance(out, str)
    assert "build a thing" in out