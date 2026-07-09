# codeweave Skill Registry

| Skill | Phase | Used by | Priority |
|-------|-------|---------|----------|
| [codeweave-coder](./codeweave-coder/SKILL.md) | 5 | Coder Agent | 50 |
| [codeweave-reviewer](./codeweave-reviewer/SKILL.md) | 5 | Reviewer Agent | 80 |

## 加新 Skill

1. 在 `codeweave-xxx/` 下创建 `SKILL.md` 文件
2. YAML frontmatter:`name / description / when_to_use / priority` (可省 `model_hint`)
3. Markdown body(可省):`## Workflow / Examples / Pitfalls`
4. 跑 `python -c "from codeweave.skills import discover_skills, load_skills_for; print(load_skills_for('coder'))"` 验证

## 扫描

`codeweave/skills/security.py::scan_skill_for_injection` 会在加载时跑:
- 检测 `print(` / `console.log(` / `__import__` / `eval(` / `exec(` / `subprocess.X(` / `os.system(`
- 命中 ≥1 → warning(Phase 5),Phase 7 升级为 skip + 上报
