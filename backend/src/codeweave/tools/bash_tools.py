"""Bash 工具:run_bash(含危险命令 HITL interrupt)。

危险命令检测在文件顶部,方便维护;run_bash 在文件下半部分。
"""
from __future__ import annotations

import re


# 危险命令正则列表(任一命中即视为危险)
# 故意保守宁可误报也不漏报(误报只是多一次确认,漏报是数据丢失)
DANGEROUS_PATTERNS: list[str] = [
    r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\S*",        # rm -rf / / rm -f /etc 等
    r"\bdd\s+.*of=/dev/",                              # dd 写裸设备
    r"\bmkfs\b",                                       # 格式化
    r":\(\)\s*\{.*\};:",                              # fork bomb
    r"\bchmod\s+-R\s+777\s+/\S*",                      # 全开根目录权限
    r"\bcurl\s+.*\|\s*bash\b",                         # 远程脚本直跑
]

# 编译后的正则(性能优化,避免每次调用重新编译)
_COMPILED: list[re.Pattern[str]] = [re.compile(p) for p in DANGEROUS_PATTERNS]


def is_dangerous(cmd: str) -> bool:
    """判断 Bash 命令是否命中危险模式。

    Args:
        cmd: 完整 shell 命令字符串。

    Returns:
        命中任一危险模式则返回 True。
    """
    return any(p.search(cmd) for p in _COMPILED)


# run_bash 在 Task 7 追加