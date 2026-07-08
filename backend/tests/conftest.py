"""Pytest session 配置。

在 PATH 中添加常见 ripgrep 安装位置,以便 grep_files 工具能找到 rg.exe。
生产环境应当将 ripgrep 安装到系统 PATH。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


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

    # Tests that don't touch the LLM still trigger Settings() validation
    # (because db.base imports get_settings eagerly). Set a dummy key so
    # pydantic-settings doesn't blow up during collection. Tests that DO
    # call LLMs override this with their own monkeypatch.setenv.
    # Don't override MODEL_NAME here — test_settings_has_defaults asserts
    # the default ("deepseek-v4-flash") holds when MODEL_NAME is unset.
    os.environ.setdefault("OPENAI_API_KEY", "sk-test")
    os.environ.setdefault("OPENAI_BASE_URL", "https://example.invalid/v1")
    # Avoid eagerly attempting to import psycopg2 in db.base._build_engine()
    # during test collection — we declare psycopg[binary]>=3.2 in pyproject
    # (no psycopg2), so the project's URL must use the +psycopg dialect. Unit
    # tests that only inspect metadata don't open a connection. Integration
    # tests that DO connect should set their own DATABASE_URL.
    if "DATABASE_URL" not in os.environ:
        os.environ["DATABASE_URL"] = (
            "postgresql+psycopg://codeweave:codeweave_dev@localhost:5432/codeweave"
        )
    else:
        # 用户在 env 传的 DATABASE_URL,强制加 +psycopg 后缀(若未指定 dialect),
        # 避免 SQLAlchemy 默认去 import psycopg2 而抛 ModuleNotFoundError。
        existing = os.environ["DATABASE_URL"]
        if existing.startswith("postgresql://") and "+psycopg" not in existing \
                and "+psycopg2" not in existing:
            os.environ["DATABASE_URL"] = existing.replace(
                "postgresql://", "postgresql+psycopg://", 1,
            )


@pytest.fixture
def fake_checkpointer(monkeypatch):
    """把 ``codeweave.tasks.compact`` 内的 checkpointer 替换为 MagicMock。

    返回 mock,默认 ``get_state(...).values = {"messages": []}``,测试可
    直接修改 ``mock.get_state.return_value.values`` 注入自定义 messages。

    Returns:
        已 patch 进 ``codeweave.tasks.compact._get_checkpointer`` 的 MagicMock。
    """
    from unittest.mock import MagicMock

    ck = MagicMock()
    ck.get_state.return_value.values = {"messages": []}
    monkeypatch.setattr("codeweave.tasks.compact._get_checkpointer", lambda: ck)
    return ck


@pytest.fixture
def celery_eager():
    """让 Celery 在当前进程同步执行,免去真实 broker。

    进入时打开 ``task_always_eager``,退出时还原,避免污染其他测试。
    """
    from codeweave.tasks.celery_app import celery_app

    prev = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    try:
        yield celery_app
    finally:
        celery_app.conf.task_always_eager = prev
