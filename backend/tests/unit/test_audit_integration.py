"""验证 Phase 2 tools 在调用后 emit tool_call audit 事件(spec §5.2)。

Step 1 失败测试 → Step 3 实现 → Step 4 全部 GREEN。
"""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.tools import ToolException
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from codeweave.persistence.audit import AuditLogger
from codeweave.tools import bash_tools, file_tools, todo_tools
from codeweave.tools.bash_tools import run_bash
from codeweave.tools.file_tools import edit_file, grep_files, read_file, write_file
from codeweave.tools.todo_tools import todo_write


# ---------------------------------------------------------------------------
# Fixture:模块级 _audit 注入 + emit 捕获
# ---------------------------------------------------------------------------


@pytest.fixture
def captured_audit():
    """为 file_tools / bash_tools / todo_tools 三个模块注入 mock AuditLogger。

    返回 ``captured`` 列表,形如 ``[(args, kwargs), ...]`` —— 与 audit.emit 签名对齐。
    测试结束时自动清理三个模块的 _audit,避免污染其他测试。
    """
    logger = AuditLogger()
    captured: list[tuple[tuple[object, ...], dict[str, object]]] = []
    logger.emit = MagicMock(side_effect=lambda *a, **kw: captured.append((a, kw)))  # type: ignore[method-assign]

    file_tools._audit = logger  # type: ignore[attr-defined]
    bash_tools._audit = logger  # type: ignore[attr-defined]
    todo_tools._audit = logger  # type: ignore[attr-defined]
    try:
        yield captured, logger
    finally:
        file_tools._audit = None  # type: ignore[attr-defined]
        bash_tools._audit = None  # type: ignore[attr-defined]
        todo_tools._audit = None  # type: ignore[attr-defined]


@pytest.fixture
def workdir(monkeypatch, tmp_path: Path) -> Path:
    """设置临时工作目录,monkeypatch 替换 file_tools.WORK_DIR。"""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(file_tools, "WORK_DIR", work.resolve())
    return work


# ---------------------------------------------------------------------------
# file_tools
# ---------------------------------------------------------------------------


def test_read_file_emits_tool_call_audit(workdir: Path, captured_audit):
    """read_file 成功后 emit tool_call,thread_id 通过 kwarg 传入。"""
    captured, _ = captured_audit
    p = workdir / "a.txt"
    p.write_text("hello", encoding="utf-8")

    read_file(path=str(p), thread_id="t-1")

    assert len(captured) == 1
    args, kwargs = captured[0]
    kind = args[0]
    assert kind == "tool_call"
    assert kwargs["thread_id"] == "t-1"
    payload = args[1]
    assert payload["tool"] == "read_file"
    assert payload["args"]["path"] == str(p)
    assert "hello" in payload["result_summary"]
    assert isinstance(kwargs["duration_ms"], int)


def test_write_file_emits_tool_call_audit(workdir: Path, captured_audit):
    """write_file 成功后 emit tool_call。"""
    captured, _ = captured_audit
    p = workdir / "out.txt"

    write_file(path=str(p), content="data", thread_id="t-1")

    assert len(captured) == 1
    args, kwargs = captured[0]
    assert args[0] == "tool_call"
    assert args[1]["tool"] == "write_file"
    assert args[1]["args"]["path"] == str(p)
    assert args[1]["args"]["content"] == "data"
    assert kwargs["thread_id"] == "t-1"


def test_edit_file_emits_tool_call_audit(workdir: Path, captured_audit):
    """edit_file 成功后 emit tool_call。"""
    captured, _ = captured_audit
    p = workdir / "code.py"
    p.write_text("def foo():\n    return 1\n", encoding="utf-8")

    edit_file(
        path=str(p),
        old_text="    return 1",
        new_text="    return 2",
        thread_id="t-1",
    )

    assert len(captured) == 1
    args, kwargs = captured[0]
    assert args[0] == "tool_call"
    assert args[1]["tool"] == "edit_file"
    assert kwargs["thread_id"] == "t-1"


def test_grep_files_emits_tool_call_audit(workdir: Path, captured_audit):
    """grep_files 成功后 emit tool_call。"""
    captured, _ = captured_audit
    (workdir / "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")

    grep_files(pattern="def foo", path=str(workdir), glob="*.py", thread_id="t-1")

    assert len(captured) == 1
    args, kwargs = captured[0]
    assert args[0] == "tool_call"
    assert args[1]["tool"] == "grep_files"
    assert kwargs["thread_id"] == "t-1"


# ---------------------------------------------------------------------------
# bash_tools
# ---------------------------------------------------------------------------


def test_run_bash_emits_tool_call_audit(captured_audit):
    """run_bash 安全命令成功后 emit tool_call。"""
    captured, _ = captured_audit
    out = run_bash(command="echo hello", thread_id="t-1")

    assert "hello" in out
    assert len(captured) == 1
    args, kwargs = captured[0]
    assert args[0] == "tool_call"
    assert args[1]["tool"] == "run_bash"
    assert kwargs["thread_id"] == "t-1"


def test_run_bash_dangerous_emits_audit_on_interrupt(captured_audit):
    """run_bash 危险命令触发 HITL interrupt 时,emit hitl_interrupt;拒绝后 emit tool_call。"""
    captured, _ = captured_audit

    class S(TypedDict, total=False):
        out: str
        error: str

    def runner(s):
        try:
            out = run_bash(command="rm -rf /tmp/safe_simulation", thread_id="t-hitl")
            return {"out": out}
        except ToolException as e:
            return {"error": str(e)}

    g = StateGraph(S)
    g.add_node("runner", runner)
    g.add_edge("__start__", "runner")
    g.add_edge("runner", END)
    app = g.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t1"}}

    app.invoke({}, config=config)
    from langgraph.types import Command

    app.invoke(Command(resume={"approved": False}), config=config)

    # 至少有一条 hitl_interrupt(初次)和一条 tool_call(拒绝路径)
    kinds = [c[0][0] for c in captured]
    thread_ids = {c[1].get("thread_id") for c in captured}
    assert "hitl_interrupt" in kinds
    assert "tool_call" in kinds
    assert "t-hitl" in thread_ids


# ---------------------------------------------------------------------------
# todo_tools
# ---------------------------------------------------------------------------


def test_todo_write_emits_tool_call_audit(captured_audit):
    """todo_write 成功后 emit tool_call。"""
    captured, _ = captured_audit
    todos = [
        {"id": "1", "content": "A", "status": "pending", "activeform": "Doing A"},
    ]
    todo_write(todos=todos, thread_id="t-1")

    assert len(captured) == 1
    args, kwargs = captured[0]
    assert args[0] == "tool_call"
    assert args[1]["tool"] == "todo_write"
    assert args[1]["args"]["todo_count"] == 1
    assert kwargs["thread_id"] == "t-1"


# ---------------------------------------------------------------------------
# 关闭 audit 时,工具仍正常工作(不依赖 audit)
# ---------------------------------------------------------------------------


def test_tools_work_without_audit_logger(workdir: Path):
    """_audit=None 时,工具仍正常工作,不抛异常、不 emit。"""
    assert file_tools._audit is None  # type: ignore[attr-defined]
    p = workdir / "x.txt"
    p.write_text("data", encoding="utf-8")
    result = read_file(path=str(p))
    assert result == "data"


def test_audit_failure_does_not_break_tool(workdir: Path, monkeypatch):
    """audit logger emit 抛异常时,工具调用仍返回正常结果。"""
    bad_logger = MagicMock(spec=AuditLogger)
    bad_logger.emit.side_effect = RuntimeError("db down")
    file_tools._audit = bad_logger  # type: ignore[attr-defined]
    try:
        p = workdir / "x.txt"
        p.write_text("hi", encoding="utf-8")
        result = read_file(path=str(p), thread_id="t")
        assert result == "hi"
    finally:
        file_tools._audit = None  # type: ignore[attr-defined]