"""敏感路径 + Skill injection scanner 测试(spec §5.3 Layer 3)。"""
from pathlib import Path

import pytest  # noqa: F401

from codeweave.skills.security import (
    is_sensitive_path,
    scan_skill_for_injection,
    SKILL_INJECTION_PATTERNS,
)


# is_sensitive_path
def test_sensitive_blocks_dotenv():
    assert is_sensitive_path(Path("/tmp/.env/config"))


def test_sensitive_blocks_dot_ssh():
    assert is_sensitive_path(Path("/home/user/.ssh/id_rsa"))


def test_sensitive_blocks_etc():
    assert is_sensitive_path(Path("/etc/passwd"))


def test_sensitive_passes_normal_path():
    assert not is_sensitive_path(Path("backend/src/codeweave/api/main.py"))


def test_sensitive_handles_windows_paths():
    p = Path("C:\\Users\\foo\\.ssh\\id_rsa")
    assert is_sensitive_path(p)


# scan_skill_for_injection
def test_scan_detects_print():
    body = "## Workflow\n1. run `print('hello')`\n"
    flagged = scan_skill_for_injection(body)
    assert any("print" in f for f in flagged)


def test_scan_detects_console_log():
    body = "console.log('debug')\nprint(res)\n"
    flagged = scan_skill_for_injection(body)
    assert len(flagged) == 2  # console.log + print 都命中


def test_scan_detects_eval():
    body = "import os; eval(input())\n"
    flagged = scan_skill_for_injection(body)
    assert any("eval" in f for f in flagged)


def test_scan_detects_subprocess():
    body = "subprocess.Popen(['ls'])\n"
    flagged = scan_skill_for_injection(body)
    assert any("subprocess" in f for f in flagged)


def test_scan_passes_clean_body():
    body = "## Workflow\n1. Read the diff carefully\n2. Check tests\n"
    flagged = scan_skill_for_injection(body)
    assert flagged == []


def test_scan_handles_multiline():
    body = (
        "## Examples\n"
        "```python\n"
        "print('hi')  # 调试\n"
        "```\n"
    )
    flagged = scan_skill_for_injection(body)
    assert any("print" in f for f in flagged)


def test_pattern_count_matches_documented():
    """防止有人偷偷减 pattern 数,得 ≥ 4 类(spec §5.3 列了 5+)。"""
    assert len(SKILL_INJECTION_PATTERNS) >= 4
