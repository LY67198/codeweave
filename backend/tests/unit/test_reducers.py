from codeweave.state.reducers import merge_todos, trim_agent_history


def test_merge_todos_adds_new():
    existing = [{"id": "1", "content": "old", "status": "pending", "activeform": "old"}]
    update = [{"id": "2", "content": "new", "status": "pending", "activeform": "new"}]
    result = merge_todos(existing, update)
    assert len(result) == 2
    assert {t["id"] for t in result} == {"1", "2"}


def test_merge_todos_overwrites_existing():
    existing = [{"id": "1", "content": "old", "status": "pending", "activeform": "old"}]
    update = [{"id": "1", "content": "updated", "status": "completed", "activeform": "updated"}]
    result = merge_todos(existing, update)
    assert len(result) == 1
    assert result[0]["content"] == "updated"
    assert result[0]["status"] == "completed"


def test_trim_agent_history_keeps_last_10():
    existing = [{"n": i} for i in range(15)]
    update = [{"n": i} for i in range(15, 20)]
    result = trim_agent_history(existing, update)
    assert len(result) == 10
    assert result[0]["n"] == 10
    assert result[-1]["n"] == 19
