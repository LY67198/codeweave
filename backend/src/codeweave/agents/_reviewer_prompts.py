"""Reviewer system prompt 拼装(spec §2.4)。

Reviewer 与 Coder 共享 Skill 资源加载机制(``load_skills_for`` /
``skills_to_prompt``),但 Reviewer 的 system prompt 强调 **只读** 与
**严格 JSON 输出**。
"""
from __future__ import annotations

from codeweave.skills.loader import skills_to_prompt
from codeweave.skills.schemas import Skill

# Reviewer 是只读角色 — 不能也不应该修改代码。
# Skill 资源由 spec 决定,Reviewer 评审时必须严格按 skill 描述执行。
_REVIEWER_BODY: str = (
    "你是 codeweave Reviewer。只读工具 — 你不能也不应该修改代码。\n"
    "skill 资源由 spec 决定,你 review 必须严格按 skill 描述执行。\n"
    "\n"
    "你 review 一段 diff,对应原始请求:\n"
)


def render_reviewer_prompt(
    *,
    diff: str,
    original_request: str,
    skills: list[Skill],
) -> str:
    """拼装 Reviewer 的 system prompt 字符串。

    Args:
        diff: 上轮 Coder 产出的 unified diff 文本。
        original_request: 用户的原始修改请求。
        skills: 该 reviewer 关联的 Skill 资源列表。

    Returns:
        完整的 system prompt,末尾含严格的 JSON 输出格式约束。
    """
    parts: list[str | None] = [
        skills_to_prompt(skills),
        "",
        _REVIEWER_BODY,
        f"原始请求: {original_request}",
        "",
        "<diff>",
        diff[:30000],  # 截断过大 diff(超 SSE payload 安全)
        "</diff>",
        "",
        'Output STRICTLY 一段 JSON,不要其他文字,不要 ``` 包装:\n'
        '{"accept": bool, "score": int 0-10, "feedback": str, "risk_flags": list[str]}',
    ]
    return "\n".join(p for p in parts if p is not None)


__all__ = ["render_reviewer_prompt"]