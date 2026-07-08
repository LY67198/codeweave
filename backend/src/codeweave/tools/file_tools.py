"""文件工具:read_file / write_file / edit_file / grep_files。

所有工具入口都做 WORK_DIR 路径校验,防止 Agent 越权访问。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

from langchain_core.tools import ToolException

from codeweave.tools.registry import register


WORK_DIR: Path = Path(os.environ.get("CODEWEAVE_CWD", ".")).resolve()

# 读文件最大字节数(超过则报错,避免 LLM 一次吞掉大文件撑爆上下文)
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB

# 写文件最大字节数
MAX_WRITE_SIZE = 512 * 1024  # 512 KB


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
) -> str:
    """读取文件内容,支持 offset/limit 分页。

    Args:
        path: 文件路径。
        offset: 起始行号,默认 0。
        limit: 读取行数,默认 2000。

    Returns:
        文件内容字符串。

    Raises:
        ToolException: 文件不存在、过大、路径越界。
    """
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
    return "".join(lines[offset : offset + limit])


@register(name="write_file", plan_mode_safe=False, requires_permission=False, category="file")
def write_file(
    path: Annotated[str, "目标文件路径(相对于工作目录,会自动创建中间目录)"],
    content: Annotated[str, "要写入的完整文件内容"],
) -> str:
    """写入文件(覆盖),自动创建中间目录。

    Args:
        path: 目标文件路径。
        content: 完整内容。

    Returns:
        写入成功的提示(含字节数)。

    Raises:
        ToolException: 内容过大或路径越界。
    """
    p = _check_path(path)
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_WRITE_SIZE:
        raise ToolException(
            f"内容过大: {len(content_bytes)} bytes (上限 {MAX_WRITE_SIZE})"
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content_bytes)
    return f"已写入 {path} ({len(content_bytes)} bytes)"


@register(name="edit_file", plan_mode_safe=False, requires_permission=False, category="file")
def edit_file(
    path: Annotated[str, "目标文件路径(相对于工作目录)"],
    old_text: Annotated[str, "要被替换的原文本(必须唯一匹配)"],
    new_text: Annotated[str, "替换后的新文本"],
) -> str:
    """精确字符串替换编辑文件。

    Args:
        path: 目标文件路径。
        old_text: 必须唯一匹配文件中某段子串。
        new_text: 替换内容。

    Returns:
        替换成功的提示。

    Raises:
        ToolException: 0 处或 >1 处匹配,或路径越界。
    """
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
    return f"已在 {path} 中完成替换"


def grep_files(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
    """grep_files 占位 — Task 5 实装时删除此函数。"""
    raise NotImplementedError("grep_files 尚未实现,见 Task 5")
