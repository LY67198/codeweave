"""Bash 工具:run_bash(含危险命令 HITL interrupt)。

危险命令检测在文件顶部,方便维护;run_bash 在文件下半部分。

Phase 3 (Task 10) 起,run_bash 调用结束后会通过模块级 ``_audit`` 全局变量
emit ``tool_call`` audit 事件(若 ``_audit`` 为 ``None`` 则跳过,工具仍正常工作)。
"""
from __future__ import annotations

import re
import time
from typing import Annotated, Any

from codeweave.persistence.audit import AuditLogger


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


# ---------------------------------------------------------------------------
# Audit 集成(Phase 3 Task 10)
# ---------------------------------------------------------------------------

# 模块级 AuditLogger 句柄。默认 None,表示无 audit;测试 / graph 启动后可注入。
_audit: AuditLogger | None = None


def set_audit_logger(logger: AuditLogger | None) -> None:
    """注入 / 清除模块级 AuditLogger。

    Args:
        logger: AuditLogger 实例,或 None。
    """
    global _audit
    _audit = logger


def _emit_tool_call(
    tool_name: str,
    args: dict[str, Any],
    result: Any,
    duration_ms: int,
    thread_id: str,
) -> None:
    """emit ``tool_call`` audit 事件。失败吞掉异常,业务继续。

    Args:
        tool_name: 工具名(用于 payload.tool)。
        args: 工具调用参数(用于 payload.args)。
        result: 工具返回值(截断到 200 字符写入 payload.result_summary)。
        duration_ms: 调用耗时(毫秒)。
        thread_id: 关联的 LangGraph thread_id,缺省 ``"<no-thread>"``。
    """
    if _audit is None:
        return
    try:
        result_summary = repr(result)[:200]
        _audit.emit(
            "tool_call",
            {"tool": tool_name, "args": args, "result_summary": result_summary},
            thread_id=thread_id,
            duration_ms=duration_ms,
        )
    except Exception:  # noqa: BLE001
        # audit 失败不影响工具返回值(spec §5.3)
        pass


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
    thread_id: Annotated[str, "LangGraph thread_id(审计用)"] = "<no-thread>",
) -> str:
    """在 shell 中执行一条命令。

    危险命令(如 ``rm -rf /`` / ``dd of=/dev/sda`` / ``mkfs`` / fork bomb /
    全开权限 / 远程脚本直跑)会触发 HITL interrupt,暂停 graph 等待用户批准。

    Args:
        command: 完整 shell 命令。
        thread_id: LangGraph thread_id,用于 audit 关联,默认 ``"<no-thread>"``。

    Returns:
        stdout 字符串(超 _MAX_OUTPUT 字符则截断)。

    Raises:
        ToolException: 超时、用户拒绝、或子进程错误。
    """
    start = time.monotonic()
    is_dangerous_cmd = is_dangerous(command)

    # 危险命令且 audit 已注入时,先记录 hitl_interrupt 事件(spec §5.2)
    if _audit is not None and is_dangerous_cmd:
        try:
            _audit.emit(
                "hitl_interrupt",
                {"command_preview": command[:200]},
                thread_id=thread_id,
            )
        except Exception:  # noqa: BLE001
            pass

    if is_dangerous_cmd:
        approval = interrupt({
            "type": "bash_permission_required",
            "command": command,
            "reason": "matched dangerous pattern",
        })
        if not approval.get("approved"):
            duration_ms = int((time.monotonic() - start) * 1000)
            _emit_tool_call(
                "run_bash",
                {"command": command[:200]},
                f"用户拒绝执行: {command}",
                duration_ms,
                thread_id,
            )
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
        duration_ms = int((time.monotonic() - start) * 1000)
        _emit_tool_call(
            "run_bash",
            {"command": command[:200]},
            f"Bash 超时(>{_BASH_TIMEOUT}s): {command}",
            duration_ms,
            thread_id,
        )
        raise ToolException(f"Bash 超时(>{_BASH_TIMEOUT}s): {command}") from e

    output = (proc.stdout or "") + (proc.stderr or "")
    if len(output) > _MAX_OUTPUT:
        output = output[:_MAX_OUTPUT] + f"\n[truncated, {len(output) - _MAX_OUTPUT} more chars]"

    duration_ms = int((time.monotonic() - start) * 1000)
    _emit_tool_call(
        "run_bash",
        {"command": command[:200]},
        output,
        duration_ms,
        thread_id,
    )
    return output