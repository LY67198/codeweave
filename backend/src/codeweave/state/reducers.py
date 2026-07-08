from typing import Any


def merge_todos(existing: list[dict], update: list[dict]) -> list[dict]:
    """按 id 合并 todos：覆盖已存在的项，追加新的项。"""
    by_id: dict[str, dict] = {}
    for todo in (existing or []):
        todo_id = todo.get("id")
        if todo_id:
            by_id[todo_id] = todo
    for todo in (update or []):
        todo_id = todo.get("id")
        if todo_id:
            by_id[todo_id] = todo
    return list(by_id.values())


def trim_agent_history(
    existing: list[dict] | None,
    update: list[dict] | None,
) -> list[dict]:
    """仅保留 agent_history 中最后 10 条记录。"""
    combined = (existing or []) + (update or [])
    return combined[-10:]


def replace_if_set(existing: Any, update: Any) -> Any:
    """若 update 非 None 则使用 update，否则保留 existing。"""
    return update if update is not None else existing
