"""Executor Subgraph 与 Tool 系统集成测试。

覆盖:
- Tool Registry 6 工具在 execute 模式全部注册
- Plan 模式过滤到 read-only 工具
- Bash HITL interrupt + resume 流程(端到端)
- Read → Write → Grep 真实文件操作的 happy path
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from codeweave.tools import get_tools_for_mode
from codeweave.tools.bash_tools import run_bash
from codeweave.tools.file_tools import grep_files, read_file, write_file
import codeweave.tools.file_tools as file_tools


def test_execute_mode_has_all_six_tools():
    """execute 模式应该返回 6 个工具:read/write/edit/grep/bash/todo_write。"""
    tools = get_tools_for_mode("execute")
    tool_names = {t.name for t in tools}
    assert tool_names == {
        "read_file", "write_file", "edit_file",
        "grep_files", "run_bash", "todo_write",
    }


def test_plan_mode_filters_to_read_only():
    """plan 模式应该只有 read_file 和 grep_files 两个只读工具。"""
    tools = get_tools_for_mode("plan")
    tool_names = {t.name for t in tools}
    assert tool_names == {"read_file", "grep_files"}


def test_bash_interrupt_resume_flow():
    """Bash 危险命令触发 interrupt,resume 后正常执行。"""
    class S(TypedDict, total=False):
        out: str

    def runner(s):
        out = run_bash(command="echo rm -rf /tmp/cancel_simulate")
        return {"out": out}

    g = StateGraph(S)
    g.add_node("runner", runner)
    g.add_edge("__start__", "runner")
    g.add_edge("runner", END)
    app = g.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t_int"}}

    # 第一次:中断
    result = app.invoke({}, config=config)
    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert payload["type"] == "bash_permission_required"
    assert "rm -rf /" in payload["command"]

    # 第二次:批准并恢复
    resumed = app.invoke(Command(resume={"approved": True}), config=config)
    assert "cancel_simulate" in resumed["out"]


def test_bash_reject_flow():
    """Bash 危险命令被拒绝后抛 ToolException。"""
    from langchain_core.tools import ToolException

    class S(TypedDict, total=False):
        out: str
        error: str

    def runner(s):
        try:
            out = run_bash(command="echo rm -rf /tmp/reject_int_test")
            return {"out": out}
        except ToolException as e:
            return {"error": str(e)}

    g = StateGraph(S)
    g.add_node("runner", runner)
    g.add_edge("__start__", "runner")
    g.add_edge("runner", END)
    app = g.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t_rej"}}

    app.invoke({}, config=config)
    resumed = app.invoke(Command(resume={"approved": False}), config=config)
    assert "拒绝" in resumed["error"]


def test_executor_happy_path_read_write_grep(tmp_path: Path, monkeypatch):
    """端到端 read → write → grep 真实文件操作(临时 git 仓库)。"""
    # 初始化 git 仓库作为 fixture
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

    # monkeypatch WORK_DIR 指向临时仓库
    original_wd = file_tools.WORK_DIR
    file_tools.WORK_DIR = tmp_path.resolve()
    try:
        # read
        content = read_file(path="f.txt")
        assert "hello" in content

        # write
        write_file(path="g.txt", content="world\n")
        assert (tmp_path / "g.txt").exists()
        assert (tmp_path / "g.txt").read_text(encoding="utf-8") == "world\n"

        # grep
        result = grep_files(pattern="world", path=str(tmp_path), glob="*.txt")
        assert "g.txt" in result
    finally:
        file_tools.WORK_DIR = original_wd
