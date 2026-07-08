"""文件工具(read_file / write_file / edit_file / grep_files)单元测试。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from langchain_core.tools import ToolException

from codeweave.tools import file_tools
from codeweave.tools.file_tools import edit_file, grep_files, read_file, write_file


@pytest.fixture
def workdir(monkeypatch, tmp_path: Path) -> Path:
    """设置临时工作目录,monkeypatch 替换 WORK_DIR。"""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(file_tools, "WORK_DIR", work.resolve())
    return work


def test_read_file_returns_content(workdir: Path):
    """read_file 正常读取已有文件。"""
    p = workdir / "hello.txt"
    p.write_text("hello world\n", encoding="utf-8")
    result = read_file(path=str(p))
    assert result == "hello world\n"


def test_read_file_offset_and_limit(workdir: Path):
    """offset + limit 实现分页读取。"""
    p = workdir / "lines.txt"
    p.write_text("\n".join(f"line{i}" for i in range(10)), encoding="utf-8")
    result = read_file(path=str(p), offset=2, limit=3)
    assert result == "line2\nline3\nline4\n"


def test_read_file_not_found_raises(workdir: Path):
    """文件不存在时抛 ToolException。"""
    p = workdir / "missing.txt"
    with pytest.raises(ToolException, match="(不存在|not found|No such)"):
        read_file(path=str(p))


def test_read_file_too_large_raises(workdir: Path):
    """文件 > 1MB 时抛 ToolException(不读超大文件)。"""
    p = workdir / "big.bin"
    p.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB
    with pytest.raises(ToolException, match="(过大|too large|1MB)"):
        read_file(path=str(p))


def test_read_file_path_traversal_blocked(workdir: Path):
    """路径逃出 WORK_DIR 时抛 ToolException。"""
    outside = workdir.parent / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(ToolException, match="(workdir|escapes|外)"):
        read_file(path=str(outside))
