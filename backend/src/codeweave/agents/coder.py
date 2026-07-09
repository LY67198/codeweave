"""Coder Agent — Maker 半边(spec §3.2)。

读取 SKILL.md 资源 + 调 LLM bind_tools + run_tools_and_diff 产 unified diff。
纯逻辑(node function),不接 graph。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from codeweave.agents._coder_diff import run_tools_and_diff
from codeweave.agents._coder_prompts import render_coder_prompt
from codeweave.config.model import get_chat_model
from codeweave.config.settings import get_settings
from codeweave.persistence.audit import AuditLogger
from codeweave.skills.loader import load_skills_for
from codeweave.skills.state import CodeModState

logger = logging.getLogger(__name__)
_audit = AuditLogger()

# repo_root Phase 5 简化为 git repo root;Phase 7 引入 git worktree 时改
# backend/src/codeweave/agents → 仓库根(D:/Mini_Code)
REPO_ROOT = Path(__file__).resolve().parents[4]


def coder_node(state: CodeModState) -> dict[str, Any]:
    """读取 SKILL.md 资源 + 调 LLM bind_tools,产 unified diff + retry_count++。

    Args:
        state: ``CodeModState``,至少含 ``request`` / ``thread_id``。

    Returns:
        包含 ``coder_diff`` / ``coder_message`` / ``retry_count`` 的部分 state 更新。
    """
    settings = get_settings()
    skills = load_skills_for("coder", roots=[Path(settings.skills_root)])

    sys_prompt = render_coder_prompt(
        request=state["request"],
        prev_diff=state.get("coder_diff"),
        prev_feedback=(state.get("reviewer_decision") or {}).get("feedback"),
        retry_count=state.get("retry_count", 0),
        max_retries=settings.code_mod_max_retries,
        skills=skills,
    )

    from langchain_core.messages import HumanMessage

    # system 消息用 dict 形式,与 plan test_coder.py 中
    # `msgs[0]["content"]` 的访问方式保持一致。
    msgs: list[Any] = [
        {"role": "system", "content": sys_prompt},
        HumanMessage(content=state["request"]),
    ]
    llm = get_chat_model(temperature=0.0)
    response = llm.bind_tools(
        _get_coder_tools()
    ).invoke(msgs)

    tool_results, diff_text, writes = run_tools_and_diff(
        response, repo_root=REPO_ROOT
    )

    _audit.emit(
        "coder_tool_executed",
        {
            "count": len(tool_results),
            "writes": [w for w, ok in writes.items() if ok],
            "diff_size": len(diff_text),
        },
        thread_id=state.get("thread_id", "unknown"),
    )

    return {
        "coder_diff": diff_text,
        "coder_message": tool_results_summary(tool_results),
        "retry_count": state.get("retry_count", 0) + 1,
    }


def tool_results_summary(results: list[dict[str, Any]]) -> str:
    """把 tools 跑完后的 results 列表压成短文本,进 audit 与状态。

    Args:
        results: ``run_tools_and_diff`` 产出的结果列表。

    Returns:
        多行字符串,每行 ``[OK|FAIL] <tool> <path|output>``。空列表返回 ``"(no tool calls)"``。
    """
    lines: list[str] = []
    for r in results[:10]:
        status = "OK" if r.get("ok") else f"FAIL({r.get('err')})"
        path_or_output = r.get("path") or str(r.get("output", ""))[:60]
        lines.append(f"  [{status}] {r.get('tool')} {path_or_output}")
    if len(results) > 10:
        lines.append(f"  ... and {len(results) - 10} more")
    return "\n".join(lines) if lines else "(no tool calls)"


def _get_coder_tools() -> list[Any]:
    """导入 Phase 2 的 tool 实例(走已注册的 langchain 工具)。

    函数体内 lazy import,避免 coder.py 顶层 import 整个工具链(里面要查 PATH 找 rg)。

    Returns:
        LangChain BaseTool 列表,可直接传给 ``llm.bind_tools(...)``。
    """
    from codeweave.tools.bash_tools import run_bash
    from codeweave.tools.file_tools import edit_file, grep_files, read_file, write_file
    return [read_file, write_file, edit_file, grep_files, run_bash]


__all__ = ["coder_node", "tool_results_summary", "REPO_ROOT"]