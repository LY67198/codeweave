from typing import Any


def merge_todos(existing: list[dict], update: list[dict]) -> list[dict]:
    """Merge todos by id: overwrite existing, append new."""
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
    """Keep only last 10 entries in agent_history."""
    combined = (existing or []) + (update or [])
    return combined[-10:]


def replace_if_set(existing: Any, update: Any) -> Any:
    """Use update if not None, otherwise keep existing."""
    return update if update is not None else existing
