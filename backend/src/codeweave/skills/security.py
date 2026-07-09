"""5 层权限防御 Layer 3(Sensitive 目录硬阻止)+ Skill 文件 content injection scanner(spec §5.3)。

arXiv skill 论文:73.5% leak 来自 print/console.log 调试输出;~90% 不需权限。
Phase 5 同时做:
1. `is_sensitive_path`: coder 写文件前路径判定
2. `scan_skill_for_injection`: skill 加载时拒有问题的 skill
"""
from __future__ import annotations

import re
from pathlib import Path

# Layer 3 spec
SENSITIVE_PATH_PREFIXES = (
    ".ssh", ".aws", ".gcp", ".azure", ".kube",
    ".docker", ".env", ".netrc",
    "/etc", "/etc/pam.d",
    "/usr/local/etc", "/var/log", "/private",
)


def is_sensitive_path(p: Path) -> bool:
    """命中任一 prefix 返回 True。Windows 路径 \\ → / 归一化。"""
    try:
        resolved = str(p.resolve()).replace("\\", "/")
    except OSError:
        resolved = str(p).replace("\\", "/")
    return any(
        resolved.startswith(prefix) or f"/{prefix.lstrip('/')}" in resolved
        for prefix in SENSITIVE_PATH_PREFIXES
    )


# Skill injection scanner — pattern 名要稳定(测试依赖)
SKILL_INJECTION_PATTERNS = [
    re.compile(r"\bprint\s*\("),
    re.compile(r"console\.log\s*\("),
    re.compile(r"\b__import__\s*\("),
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"subprocess\.(Popen|call|run|check_output|check_call)\s*\("),
    re.compile(r"\bos\.system\s*\("),
]


def scan_skill_for_injection(body: str) -> list[str]:
    """返回命中的 pattern 名(人类可读)。

    Skill 加载 / commit 时各跑一次。命中数 ≥1 → warn + skip 加载(Phase 5)。
    """
    flagged = []
    for p in SKILL_INJECTION_PATTERNS:
        if p.search(body):
            flagged.append(p.pattern)
    return flagged
