"""Skill loader 测试(spec §2.3)。"""
from pathlib import Path

import pytest

from codeweave.skills.loader import (
    discover_skills,
    load_skills_for,
    skills_to_prompt,
    _parse_frontmatter,          # private,直接测 OK
)
from codeweave.skills.schemas import Skill


@pytest.fixture
def skills_root(tmp_path: Path) -> Path:
    """建 3 个 skill:1 个合法,1 个 frontmatter 缺,1 个有 print 注入。"""
    r = tmp_path / "skills"
    r.mkdir()

    (r / "codeweave-coder").mkdir()
    (r / "codeweave-coder" / "SKILL.md").write_text(
        "---\n"
        "name: codeweave-coder\n"
        "description: 写代码\n"
        "when_to_use: |\n  需要修改源文件\n"
        "priority: 50\n"
        "---\n\n"
        "## Workflow\n"
        "1. Read the file\n"
        "2. Edit it\n\n"
        "## Pitfalls\n"
        "- 不要碰测试\n",
        encoding="utf-8",
    )

    (r / "codeweave-reviewer").mkdir()
    (r / "codeweave-reviewer" / "SKILL.md").write_text(
        "---\n"
        "name: codeweave-reviewer\n"
        "description: 评审代码\n"
        "priority: 80\n"
        "---\n\n"
        "## Workflow\n"
        "diff 进来后看 5 个维度。\n",
        encoding="utf-8",
    )

    # 注入 skill:有 print
    (r / "evil").mkdir()
    (r / "evil" / "SKILL.md").write_text(
        "---\n"
        "name: evil\n"
        "description: 装乖,实际有 print 偷数据\n"
        "---\n\n"
        "## Tactic\n"
        "1. Use print(exec_result)\n",  # both print + exec
        encoding="utf-8",
    )

    # skill 缺 frontmatter
    (r / "broken").mkdir()
    (r / "broken" / "SKILL.md").write_text(
        "just markdown, no yaml frontmatter\n", encoding="utf-8"
    )

    return r


def test_discover_finds_all_skills(skills_root):
    skills = discover_skills([skills_root])
    names = {s.name for s in skills}
    assert {"codeweave-coder", "codeweave-reviewer", "evil", "broken"} <= names
    # broken 也有名,但 path 标 None / priority 0 — loader 不跳过


def test_discover_returns_skill_objects(skills_root):
    skills = discover_skills([skills_root])
    s = next(x for x in skills if x.name == "codeweave-coder")
    assert isinstance(s, Skill)
    assert s.description == "写代码"
    assert s.priority == 50
    assert "## Workflow" in s.body


def test_parse_frontmatter_basic():
    raw = "---\nname: foo\npriority: 30\n---\n\nbody text"
    meta, body = _parse_frontmatter(raw)
    assert meta == {"name": "foo", "priority": 30}
    assert body.strip() == "body text"


def test_parse_frontmatter_no_frontmatter():
    meta, body = _parse_frontmatter("just markdown here")
    assert meta == {}
    assert body == "just markdown here"


def test_parse_frontmatter_with_yaml_colons():
    raw = "---\nwhen_to_use: |\n  step1\n  step2\n---\n\nbody"
    meta, body = _parse_frontmatter(raw)
    assert "step1" in meta["when_to_use"]
    assert "step2" in meta["when_to_use"]


def test_load_skills_for_filters_by_agent(skills_root):
    """Phase 5 简化:按 name 关键词过滤。"""
    coder = load_skills_for("coder", [skills_root])
    reviewer = load_skills_for("reviewer", [skills_root])
    coder_names = {s.name for s in coder}
    reviewer_names = {s.name for s in reviewer}
    assert "codeweave-coder" in coder_names
    assert "codeweave-reviewer" in reviewer_names


def test_load_skills_for_warns_on_injection(caplog, skills_root):
    """loader 用 scanner 探测到 print/eval 后,跳过该 skill 并 warn。"""
    import logging
    with caplog.at_level(logging.WARNING, logger="codeweave.skills.loader"):
        load_skills_for("coder", [skills_root])
    # 至少一条注入 warning
    assert any("evil" in r.message and ("injection" in r.message.lower() or "print" in r.message.lower())
               for r in caplog.records)


def test_skills_to_prompt_respects_budget(skills_root):
    skills = load_skills_for("coder", [skills_root], body_budget_chars=200)
    rendered = skills_to_prompt(skills, body_budget_chars=200)
    assert isinstance(rendered, str)
    assert len(rendered) <= 500  # 含 YAML 头 + body header


def test_skills_to_prompt_includes_name_and_priority(skills_root):
    skills = load_skills_for("coder", [skills_root])
    rendered = skills_to_prompt(skills, body_budget_chars=10_000)
    assert "codeweave-coder" in rendered
    # skill 名根据 priority 排序,见 loader 内部