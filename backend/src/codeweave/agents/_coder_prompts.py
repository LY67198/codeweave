"""Coder system prompt 拼装(spec §2.4)。

`render_coder_prompt` 把 SKILL 资源 + 上轮 diff + 上轮 reviewer 反馈 + 重试计数
拼成一段 system prompt,作为 coder_node 调 LLM 时的角色设定。
"""
from __future__ import annotations

from codeweave.skills.loader import skills_to_prompt
from codeweave.skills.schemas import Skill


def render_coder_prompt(
    *,
    request: str,
    prev_diff: str | None,
    prev_feedback: str | None,
    retry_count: int,
    max_retries: int,
    skills: list[Skill],
) -> str:
    """拼装 Coder 的 system prompt。

    Args:
        request: 用户的原始请求。
        prev_diff: 上轮 Coder 产出的 unified diff(首次为 None)。
        prev_feedback: 上轮 Reviewer 给的反馈(首次为 None)。
        retry_count: 已重试次数(0 表示首次)。
        max_retries: 重试上限。
        skills: 预先加载的 Skill 列表(已按 agent 关键词过滤)。

    Returns:
        完整 system prompt 字符串,非空。
    """
    parts = [
        "你是 codeweave Coder — 代码修改专家。",
        "对只读请求(file read / grep)用工具;写代码用 file_write / file_edit / bash。",
        "禁止触碰敏感路径(.ssh / .env / /etc 等),tool 入口会拒。",
        "",
        skills_to_prompt(skills),
        "",
        f"需求:{request}",
        f"上轮 diff:{(prev_diff or '无(首次)')[:3000]}",
        f"上轮 reviewer 反馈:{(prev_feedback or '无(首次)')[:1500]}",
        f"retry_count: {retry_count}/{max_retries}",
    ]
    return "\n".join(p for p in parts if p is not None)


__all__ = ["render_coder_prompt"]