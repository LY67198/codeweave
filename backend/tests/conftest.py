"""Pytest session 配置。

在 PATH 中添加常见 ripgrep 安装位置,以便 grep_files 工具能找到 rg.exe。
生产环境应当将 ripgrep 安装到系统 PATH。
"""
from __future__ import annotations

import os
from pathlib import Path


# 开发环境中 rg.exe 的常见位置(Claude Code 缓存)
_RG_SEARCH_PATHS: list[Path] = [
    Path.home() / ".cache" / "mimocode" / "bin",
    Path.home() / ".cache" / "opencode" / "bin",
]


def pytest_configure(config):  # noqa: ARG001
    """在 pytest session 开始时把找到的 rg 路径加到 PATH。"""
    for search_path in _RG_SEARCH_PATHS:
        rg_exe = search_path / ("rg.exe" if os.name == "nt" else "rg")
        if rg_exe.exists():
            current = os.environ.get("PATH", "")
            if str(search_path) not in current:
                os.environ["PATH"] = str(search_path) + os.pathsep + current
            break
