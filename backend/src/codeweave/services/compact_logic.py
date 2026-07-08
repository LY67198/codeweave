"""Compact 摘要算法(纯函数,无 DB / LLM 副作用)。

设计:与 IO 完全解耦,便于单测覆盖边界。LLM 调用在 tasks/compact.py 里做。
"""
from __future__ import annotations

from langchain_core.messages import BaseMessage, SystemMessage
from tiktoken import get_encoding

from codeweave.prompts import render as render_template

_ENC = get_encoding("cl100k_base")


def estimate_messages_tokens(messages: list[BaseMessage]) -> int:
    """用 cl100k_base 编码器估算 messages token 数。"""
    total = 0
    for m in messages:
        content = m.content if isinstance(m.content, str) else str(m.content)
        total += len(_ENC.encode(content))
        total += 4  # role / metadata overhead 估算
    return total


def choose_compact_range(
    messages: list[BaseMessage],
    keep_last_n: int,
) -> tuple[int, int]:
    """返回 ``(keep_first, keep_last)`` 区间索引(half-open)。

    - system messages 全保
    - 最后 ``keep_last_n`` 条全保
    - 中间区间是要摘要的部分
    - 历史太短没中间区间 → 返回 ``(len(messages), len(messages))``
    """
    system_count = sum(1 for m in messages if isinstance(m, SystemMessage))
    keep_last = max(0, len(messages) - keep_last_n)
    keep_first = system_count
    if keep_first >= keep_last:
        return len(messages), len(messages)
    return keep_first, keep_last


def messages_to_history_text(messages: list[BaseMessage]) -> str:
    """渲染成纯文本,供 Jinja prompt 用。"""
    out: list[str] = []
    for m in messages:
        role = type(m).__name__.replace("Message", "").lower()
        out.append(f"[{role}] {m.content}")
    return "\n".join(out)


def render_compact_prompt(
    messages: list[BaseMessage],
    keep_last_n: int,
    max_summary_tokens: int,
) -> str:
    """构造整段摘要 prompt(单字符串)。"""
    return render_template(
        "compact.jinja",
        history_text=messages_to_history_text(messages),
        max_summary_tokens=max_summary_tokens,
    )