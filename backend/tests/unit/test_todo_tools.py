"""todo_write 工具单元测试 + merge_todos reducer 集成测试。"""
from __future__ import annotations

import pytest
from langchain_core.tools import ToolException

from codeweave.state.reducers import merge_todos
from codeweave.tools.todo_tools import todo_write


def test_todo_write_returns_input_list():
    """todo_write 应该原样返回传入的 todos 列表。"""
    todos = [
        {"id": "1", "content": "A", "status": "pending", "activeform": "Doing A"},
        {"id": "2", "content": "B", "status": "in_progress", "activeform": "Doing B"},
    ]
    result = todo_write(todos=todos)
    assert result == todos


def test_todo_write_validates_required_fields():
    """缺少必要字段的 todo 抛 ToolException。"""
    with pytest.raises(ToolException, match="(id|content|status|activeform|缺少)"):
        todo_write(todos=[{"id": "1", "content": "x"}])  # 缺 status + activeform


def test_todo_write_validates_status_enum():
    """status 必须是 pending/in_progress/completed。"""
    bad = [{"id": "1", "content": "x", "status": "weird", "activeform": "y"}]
    with pytest.raises(ToolException, match="(status|状态|invalid)"):
        todo_write(todos=bad)


def test_todo_write_filters_completed_items():
    """已完成(status=completed)的 todo 在返回前过滤掉。"""
    todos = [
        {"id": "1", "content": "Done", "status": "completed", "activeform": "Did"},
        {"id": "2", "content": "Active", "status": "in_progress", "activeform": "Doing"},
    ]
    result = todo_write(todos=todos)
    assert all(t["status"] != "completed" for t in result)
    assert any(t["id"] == "2" for t in result)


def test_merge_todos_dedupes_by_id():
    """merge_todos reducer 按 id 去重,后传入的覆盖先传入的。"""
    existing = [{"id": "1", "content": "old", "status": "pending", "activeform": "f"}]
    update = [{"id": "1", "content": "new", "status": "completed", "activeform": "f"}]
    result = merge_todos(existing, update)
    assert len(result) == 1
    assert result[0]["content"] == "new"
    assert result[0]["status"] == "completed"


def test_todo_write_then_merge_produces_state():
    """端到端:todo_write 返回的列表传给 merge_todos 得到合法 state['todos']。"""
    existing = [
        {"id": "1", "content": "A", "status": "in_progress", "activeform": "f"},
    ]
    new = todo_write(todos=[
        {"id": "1", "content": "A", "status": "completed", "activeform": "f"},
        {"id": "2", "content": "B", "status": "pending", "activeform": "f"},
    ])
    merged = merge_todos(existing, new)
    # merge_todos 是纯 dedupe(按 id upsert,不删除 existing 中未在 update 中出现的项)。
    # 1 在 todo_write 阶段被过滤掉,所以 update 只有 id=2。
    # merge_todos(existing=[id=1], update=[id=2]) → 保留 id=1(没被 update 覆盖),新增 id=2。
    # 实际应用场景:Executor 节点在 todo_write 之前应把 existing 也按 completed 过滤,
    # 或在更上层用其他机制清理已完成的 todo。这里只验证 todo_write + merge_todos 的拼接行为。
    assert len(merged) == 2
    ids = {t["id"] for t in merged}
    assert ids == {"1", "2"}