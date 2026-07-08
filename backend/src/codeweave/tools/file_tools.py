"""文件工具:read_file / write_file / edit_file / grep_files。

所有工具入口都做 WORK_DIR 路径校验,防止 Agent 越权访问。

Phase 3 (Task 10) 起,每个工具调用结束后会通过模块级 ``_audit`` 全局变量
emit ``tool_call`` audit 事件(若 ``_audit`` 为 ``None`` 则跳过,工具仍正常工作)。
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Annotated, Any

from langchain_core.tools import ToolException

from codeweave.persistence.audit import AuditLogger
from codeweave.tools.registry import register


WORK_DIR: Path = Path(os.environ.get("CODEWEAVE_CWD", ".")).resolve()

# 读文件最大字节数(超过则报错,避免 LLM 一次吞掉大文件撑爆上下文)
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB

# 写文件最大字节数
MAX_WRITE_SIZE = 512 * 1024  # 512 KB


# ---------------------------------------------------------------------------
# Audit 集成(Phase 3 Task 10)
# ---------------------------------------------------------------------------

# 模块级 AuditLogger 句柄。默认 None,表示无 audit;测试 / graph 启动后可注入。
_audit: AuditLogger | None = None


def set_audit_logger(logger: AuditLogger | None) -> None:
    """注入 / 清除模块级 AuditLogger。

    供 graph 启动阶段或测试注入使用。设为 ``None`` 表示关闭 audit。

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


def _check_path(path_str: str) -> Path:
    """校验路径在 WORK_DIR 内,返回 resolved Path。

    Args:
        path_str: 用户传入的路径字符串(可能是相对或绝对)。

    Returns:
        已 resolve 的 Path 对象。

    Raises:
        ToolException: 路径解析失败或逃出工作目录。
    """
    try:
        requested = Path(path_str)
        # 若是相对路径,基于 WORK_DIR 解析
        if not requested.is_absolute():
            requested = (WORK_DIR / requested).resolve()
        else:
            requested = requested.resolve()
    except (OSError, ValueError) as e:
        raise ToolException(f"无法解析路径 {path_str!r}: {e}") from e

    try:
        requested.relative_to(WORK_DIR)
    except ValueError as e:
        raise ToolException(
            f"路径 {path_str!r} 逃出工作目录 {WORK_DIR}(外部路径 external path)"
        ) from e

    return requested


@register(name="read_file", plan_mode_safe=True, requires_permission=False, category="file")
def read_file(
    path: Annotated[str, "要读取的文件路径(相对于工作目录)"],
    offset: Annotated[int, "起始行号(0-based)"] = 0,
    limit: Annotated[int, "读取行数上限"] = 2000,
    thread_id: Annotated[str, "LangGraph thread_id(审计用)"] = "<no-thread>",
) -> str:
    """读取文件内容,支持 offset/limit 分页。

    Args:
        path: 文件路径。
        offset: 起始行号,默认 0。
        limit: 读取行数,默认 2000。
        thread_id: LangGraph thread_id,用于 audit 关联,默认 ``"<no-thread>"``。

    Returns:
        文件内容字符串。

    Raises:
        ToolException: 文件不存在、过大、路径越界。
    """
    start = time.monotonic()
    p = _check_path(path)
    if not p.exists():
        raise ToolException(f"文件不存在: {path}")
    if not p.is_file():
        raise ToolException(f"不是普通文件: {path}")
    size = p.stat().st_size
    if size > MAX_FILE_SIZE:
        raise ToolException(f"文件过大: {size} bytes (上限 {MAX_FILE_SIZE})")
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    result = "".join(lines[offset : offset + limit])
    _emit_tool_call(
        "read_file",
        {"path": path, "offset": offset, "limit": limit},
        result,
        int((time.monotonic() - start) * 1000),
        thread_id,
    )
    return result


@register(name="write_file", plan_mode_safe=False, requires_permission=False, category="file")
def write_file(
    path: Annotated[str, "目标文件路径(相对于工作目录,会自动创建中间目录)"],
    content: Annotated[str, "要写入的完整文件内容"],
    thread_id: Annotated[str, "LangGraph thread_id(审计用)"] = "<no-thread>",
) -> str:
    """写入文件(覆盖),自动创建中间目录。

    Args:
        path: 目标文件路径。
        content: 完整内容。
        thread_id: LangGraph thread_id,用于 audit 关联,默认 ``"<no-thread>"``。

    Returns:
        写入成功的提示(含字节数)。

    Raises:
        ToolException: 内容过大或路径越界。
    """
    start = time.monotonic()
    p = _check_path(path)
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_WRITE_SIZE:
        raise ToolException(
            f"内容过大: {len(content_bytes)} bytes (上限 {MAX_WRITE_SIZE})"
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content_bytes)
    result = f"已写入 {path} ({len(content_bytes)} bytes)"
    _emit_tool_call(
        "write_file",
        {"path": path, "content": content},
        result,
        int((time.monotonic() - start) * 1000),
        thread_id,
    )
    return result


@register(name="edit_file", plan_mode_safe=False, requires_permission=False, category="file")
def edit_file(
    path: Annotated[str, "目标文件路径(相对于工作目录)"],
    old_text: Annotated[str, "要被替换的原文本(必须唯一匹配)"],
    new_text: Annotated[str, "替换后的新文本"],
    thread_id: Annotated[str, "LangGraph thread_id(审计用)"] = "<no-thread>",
) -> str:
    """精确字符串替换编辑文件。

    Args:
        path: 目标文件路径。
        old_text: 必须唯一匹配文件中某段子串。
        new_text: 替换内容。
        thread_id: LangGraph thread_id,用于 audit 关联,默认 ``"<no-thread>"``。

    Returns:
        替换成功的提示。

    Raises:
        ToolException: 0 处或 >1 处匹配,或路径越界。
    """
    start = time.monotonic()
    p = _check_path(path)
    if not p.exists():
        raise ToolException(f"文件不存在: {path}")
    size = p.stat().st_size
    if size > MAX_FILE_SIZE:
        raise ToolException(f"文件过大: {size} bytes (上限 {MAX_FILE_SIZE})")
    text = p.read_text(encoding="utf-8", errors="replace")
    occurrences = text.count(old_text)
    if occurrences == 0:
        raise ToolException(f"old_text 未找到: 在 {path} 中没有匹配,无法替换")
    if occurrences > 1:
        raise ToolException(
            f"old_text 在 {path} 中匹配了 {occurrences} 次(必须唯一),"
            f"请在 old_text 中加入更多上下文"
        )
    new_text_full = text.replace(old_text, new_text, 1)
    p.write_text(new_text_full, encoding="utf-8")
    result = f"已在 {path} 中完成替换"
    _emit_tool_call(
        "edit_file",
        {"path": path, "old_text": old_text, "new_text": new_text},
        result,
        int((time.monotonic() - start) * 1000),
        thread_id,
    )
    return result


@register(name="grep_files", plan_mode_safe=True, requires_permission=False, category="file")
def grep_files(
    pattern: Annotated[str, "正则表达式模式(ripgrep 语法)"],
    path: Annotated[str, "搜索根路径(相对于工作目录)"] = ".",
    glob: Annotated[str, "文件 glob 过滤,如 '*.py'"] = "**/*",
    max_results: Annotated[int, "最多返回的结果数"] = 50,
    thread_id: Annotated[str, "LangGraph thread_id(审计用)"] = "<no-thread>",
) -> str:
    """用 ripgrep 在文件中搜索匹配。

    Args:
        pattern: 正则模式。
        path: 搜索根(默认 "." 即工作目录)。
        glob: 文件 glob 过滤。
        max_results: 结果上限,超过则截断并标注。
        thread_id: LangGraph thread_id,用于 audit 关联,默认 ``"<no-thread>"``。

    Returns:
        ripgrep 输出(形如 ``path:line:content``),无匹配返回提示。

    Raises:
        ToolException: ripgrep 不可用、超时或路径越界。
    """
    start = time.monotonic()
    import shutil
    import subprocess

    rg = shutil.which("rg")
    if not rg:
        raise ToolException("ripgrep (rg) 未安装,无法执行 grep_files")

    root = _check_path(path)
    if not root.exists():
        raise ToolException(f"搜索路径不存在: {path}")

    try:
        proc = subprocess.run(
            [rg, "--line-number", "--no-heading", "--color=never",
             "--glob", glob, "--max-columns", "200",
             pattern, str(root)],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise ToolException("grep_files 超时(>10s),请缩小 glob") from e

    if proc.returncode not in (0, 1):  # 0=有匹配,1=无匹配
        raise ToolException(f"ripgrep 失败: {proc.stderr.strip()}")

    lines = proc.stdout.splitlines()
    if not lines:
        result = "无匹配"
    elif len(lines) > max_results:
        truncated = lines[:max_results]
        result = "\n".join(truncated) + f"\n[truncated, {len(lines) - max_results} more]"
    else:
        result = "\n".join(lines)

    _emit_tool_call(
        "grep_files",
        {"pattern": pattern, "path": path, "glob": glob, "max_results": max_results},
        result,
        int((time.monotonic() - start) * 1000),
        thread_id,
    )
    return result