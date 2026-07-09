"""Skill 文件系统 loader(spec §2.3)。

discover_skills → load_skills_for → skills_to_prompt。
SKILL.md 格式:YAML frontmatter + Markdown body(Anthropic Skills 规范兼容)。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from codeweave.skills.schemas import Skill
from codeweave.skills.security import scan_skill_for_injection

logger = logging.getLogger("codeweave.skills.loader")

# Phase 5 简化版过滤:name 与 agent 关键词匹配即纳入
_AGENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "coder": ("coder",),
    "reviewer": ("reviewer",),
}


def _parse_frontmatter(raw: str) -> tuple[dict[str, object], str]:
    """return (yaml_meta, body)。无 frontmatter 时 yaml_meta={},body=raw。"""
    if not raw.startswith("---"):
        return {}, raw
    # match 首个 '---' 之后到下一个 '---' 行的内容
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", raw, re.S)
    if not m:
        return {}, raw
    meta_raw, body = m.group(1), m.group(2)
    meta: dict[str, object] = {}
    # 极简 YAML 解析:key: value,支持 | block scalar(字面块)
    lines = meta_raw.split("\n")
    cur_key = None
    cur_val_lines: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        # key 行(无前缩进)
        if not line.startswith(" ") and ":" in line:
            if cur_key is not None:
                meta[cur_key] = _join_scalar(cur_key, cur_val_lines)
            k, _, v = line.partition(":")
            cur_key = k.strip()
            v_strip = v.strip()
            cur_val_lines = []
            # `|` 块:cur_val_lines 后续是字面
            if v_strip == "|":
                continue
            if v_strip:
                # 单行 scalar(可能带引号)
                meta[cur_key] = v_strip.strip('"').strip("'")
                cur_key = None
        elif cur_key is not None:
            # block scalar 续行
            cur_val_lines.append(line.strip())
    if cur_key is not None and cur_key not in meta:
        meta[cur_key] = _join_scalar(cur_key, cur_val_lines)

    # 类型转换(常见字段)
    if "priority" in meta:
        try:
            meta["priority"] = int(str(meta["priority"]))
        except (ValueError, TypeError):
            meta["priority"] = 0
    return meta, body


def _join_scalar(key: str, lines: list[str]) -> str:
    return "\n".join(lines).strip() if lines else ""


def _parse_sections(body: str) -> dict[str, str]:
    """## section → body 解析。Phase 5 简化:贪婪到下一个 ## 为止。"""
    sections: dict[str, str] = {}
    cur_name = "_intro"  # leading markdown before any ##
    cur_lines: list[str] = []
    for line in body.split("\n"):
        m = re.match(r"^##\s+(\S.*)$", line)
        if m:
            if cur_name:
                sections[cur_name] = "\n".join(cur_lines).strip()
            cur_name = m.group(1).strip()
            cur_lines = []
        else:
            cur_lines.append(line)
    if cur_name:
        sections[cur_name] = "\n".join(cur_lines).strip()
    return sections


def discover_skills(roots: list[Path]) -> list[Skill]:
    """Walk roots 找 SKILL.md / *.md,parse 成 Skill 列表。"""
    found: list[Skill] = []
    for root in roots:
        if not root.exists():
            continue
        for md_file in list(root.rglob("SKILL.md")) + list(root.rglob("*.md")):
            if md_file.parent == root:
                continue  # 根目录的 *.md 不读
            try:
                raw = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("skill_read_failed", extra={"path": str(md_file), "err": str(exc)})
                continue
            meta, body = _parse_frontmatter(raw)
            name = meta.get("name") or md_file.parent.name
            if not str(name).strip():
                logger.warning("skill_skip_no_name", extra={"path": str(md_file)})
                continue
            flagged = scan_skill_for_injection(body)
            if flagged:
                logger.warning(
                    "skill_injection_detected path=%s flagged=%s",
                    md_file,
                    flagged,
                )
                # Phase 5:warn 但仍加载(用户自己判断);Phase 7 改成 skip
            try:
                skill = Skill(
                    name=str(name),
                    description=str(meta.get("description", "")),
                    when_to_use=str(meta.get("when_to_use", "")),
                    priority=int(str(meta.get("priority", 0) or 0)),
                    body=body,
                    parsed_sections=_parse_sections(body),
                    path=md_file,
                )
            except ValueError:
                continue
            found.append(skill)
    # 按 priority 降序,后 load 时保留高优先级在 prompt 前
    found.sort(key=lambda s: (-s.priority, s.name))
    return found


def load_skills_for(agent: str, roots: list[Path], *, body_budget_chars: int = 4000) -> list[Skill]:
    """Filter discover 出来的 skills by agent 关键词(name 含对应关键词)。

    Phase 5 简化版:全部 skills 都 load,然后 caller 自己按 name 过滤;
    实际这里做一次兜底 name 过滤。
    """
    all_skills = discover_skills(roots)
    if agent not in _AGENT_KEYWORDS:
        return all_skills
    keywords = _AGENT_KEYWORDS[agent]
    return [s for s in all_skills if any(k in s.name.lower() for k in keywords)]


def skills_to_prompt(skills: list[Skill], *, body_budget_chars: int = 4000) -> str:
    """把 skills 拼成 system prompt 片段,按 priority + 字符预算截断。"""
    if not skills:
        return ""
    parts: list[str] = ["## 可用 Skill 资源"]
    used = 0
    for s in skills:
        head = f"\n### {s.name}(priority={s.priority}): {s.description}\n触发:{s.when_to_use or '(无条件)'}\n"
        # 预算检查
        remaining = body_budget_chars - used - len(head)
        if remaining <= 200:
            break
        body = s.body[:remaining] if len(s.body) > remaining else s.body
        used += len(head) + len(body)
        parts.append(f"{head}{body}\n")
    return "".join(parts)