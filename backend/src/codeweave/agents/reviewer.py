"""Reviewer Agent — Checker 半边(spec §3.3 / §3.4)。

独立 system prompt(无 tools),纯 JSON 输出。
对 LLM 返回文本做 json5 容错 + reject-default + audit emit。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from codeweave.agents._reviewer_prompts import render_reviewer_prompt
from codeweave.config.model import get_chat_model
from codeweave.config.settings import get_settings
from codeweave.persistence.audit import AuditLogger
from codeweave.skills.loader import load_skills_for
from codeweave.skills.schemas import ReviewerDecision
from codeweave.skills.state import CodeModState

logger = logging.getLogger(__name__)
_audit = AuditLogger()


def reviewer_node(state: CodeModState) -> dict[str, Any]:
    """独立 system prompt,无 tools,纯 JSON 输出。

    Args:
        state: ``CodeModState``,至少含 ``request`` / ``coder_diff`` /
            ``thread_id``。``coder_diff`` 必须存在,否则直接 ``AssertionError``
            (spec §3.3)。

    Returns:
        包含 ``reviewer_decision`` 的部分 state 更新,值为
        ``ReviewerDecision.model_dump()``。
    """
    assert state.get("coder_diff"), "reviewer 必须有 diff 才能审"
    settings = get_settings()
    skills = load_skills_for("reviewer", roots=[Path(settings.skills_root)])
    sys_prompt = render_reviewer_prompt(
        diff=state["coder_diff"],
        original_request=state["request"],
        skills=skills,
    )

    llm = get_chat_model(temperature=0.0)
    response = llm.invoke([
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": state["request"]},
    ])

    raw = getattr(response, "content", "") or ""
    decision = _parse_reviewer_decision(raw, default_accept=False)

    _audit.emit(
        "reviewer_decision",
        {
            "accept": decision.accept,
            "score": decision.score,
            "risk_flags": decision.risk_flags,
        },
        thread_id=state.get("thread_id", "unknown"),
    )

    return {"reviewer_decision": decision.model_dump()}


def _parse_reviewer_decision(raw: str, default_accept: bool) -> ReviewerDecision:
    """JSON parse 容错(spec §3.4)。

    解析策略(按顺序):
        1. 正则抽 `````json ... ````` / ``````` ... ``````` fence 块
        2. ``json.loads`` 标准解析
        3. 失败则尝试 ``import json5`` 做容错(trailing comma 等);
           若 ``json5`` 未安装,降级用 regex 抽 ``{...}`` 块 +
           去 trailing comma 后再 ``json.loads``
        4. 仍失败则返回 ``accept=default_accept`` 的 reject 决策,
           ``risk_flags=["json_broken"]`` + feedback 解释

    Args:
        raw: LLM 返回的原始文本。
        default_accept: parse 彻底失败时使用的 accept 默认值(测试中传 False,
            spec 倾向保守拒绝)。

    Returns:
        校验过的 ``ReviewerDecision`` 实例。
    """
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    candidate = fence.group(1) if fence else raw.strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        # json5 优先,无则降级到 regex 抽 {…} + 去 trailing comma
        try:
            import json5  # type: ignore[import-not-found]  # optional dep

            data = json5.loads(candidate)
        except ModuleNotFoundError:
            data = _regex_json_fallback(candidate)
            if data is None:
                logger.warning(
                    "reviewer_json_parse_failed",
                    extra={"err": "json5 missing + regex fallback empty", "raw_preview": raw[:200]},
                )
                return ReviewerDecision(
                    accept=default_accept,
                    score=0,
                    feedback=f"Reviewer JSON parse failed: {raw[:300]}",
                    risk_flags=["json_broken"],
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "reviewer_json_parse_failed",
                extra={"err": str(exc), "raw_preview": raw[:200]},
            )
            return ReviewerDecision(
                accept=default_accept,
                score=0,
                feedback=f"Reviewer JSON parse failed: {raw[:300]}",
                risk_flags=["json_broken"],
            )
    try:
        return ReviewerDecision.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "reviewer_pydantic_validate_failed",
            extra={"err": str(exc), "data": str(data)[:200]},
        )
        return ReviewerDecision(
            accept=default_accept,
            score=0,
            feedback=f"Reviewer output failed validation: {exc}",
            risk_flags=["validation_broken"],
        )


def _regex_json_fallback(candidate: str) -> dict[str, Any] | None:
    """无 json5 时的兜底:贪婪抽 ``{...}`` 块 + 去 trailing comma,再 json.loads。

    Phase 5 仅处理最常见的 trailing-comma 情形(spec §3.4 简化版)。
    仍失败返回 None,让 caller 走 reject-default 路径。

    Args:
        candidate: 已经抽掉 fence 的候选 JSON 文本。

    Returns:
        解析成功返回 ``dict``;失败返回 ``None``。
    """
    m = re.search(r"\{.*\}", candidate, re.S)
    if not m:
        return None
    cleaned = re.sub(r",(\s*[}\]])", r"\1", m.group(0))
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return result if isinstance(result, dict) else None


__all__ = ["reviewer_node", "_parse_reviewer_decision"]