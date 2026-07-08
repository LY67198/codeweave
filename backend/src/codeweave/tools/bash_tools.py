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


# ---------------------------------------------------------------------------
# run_bash:执行 shell 命令,危险模式触发 HITL interrupt(Task 7)
# ---------------------------------------------------------------------------

import subprocess
from typing import Annotated

from langchain_core.tools import ToolException
from langgraph.types import interrupt

from codeweave.tools.registry import register


# 输出截断上限
_MAX_OUTPUT = 10_000
# 超时秒数
_BASH_TIMEOUT = 30


@register(name="run_bash", plan_mode_safe=False, requires_permission=True, category="bash")
def run_bash(
    command: Annotated[str, "要执行的 shell 命令"],
) -> str:
    """在 shell 中执行一条命令。

    危险命令(如 ``rm -rf /`` / ``dd of=/dev/sda`` / ``mkfs`` / fork bomb /
    全开权限 / 远程脚本直跑)会触发 HITL interrupt,暂停 graph 等待用户批准。

    Args:
        command: 完整 shell 命令。

    Returns:
        stdout 字符串(超 _MAX_OUTPUT 字符则截断)。

    Raises:
        ToolException: 超时、用户拒绝、或子进程错误。
    """
    if is_dangerous(command):
        approval = interrupt({
            "type": "bash_permission_required",
            "command": command,
            "reason": "matched dangerous pattern",
        })
        if not approval.get("approved"):
            raise ToolException(f"用户拒绝执行: {command}")

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=_BASH_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise ToolException(f"Bash 超时(>{_BASH_TIMEOUT}s): {command}") from e

    output = (proc.stdout or "") + (proc.stderr or "")
    if len(output) > _MAX_OUTPUT:
        output = output[:_MAX_OUTPUT] + f"\n[truncated, {len(output) - _MAX_OUTPUT} more chars]"
    return output