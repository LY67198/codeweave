from typing import Any


def merge_todos(existing: list[dict], update: list[dict]) -> list[dict]:
    """合并 todo 列表:按 id 覆盖已存在的 todo,新增的追加到末尾。

    使用 ``id`` 作为唯一键,确保合并后每个 ``id`` 在结果中只出现一次。
    未携带 ``id`` 的条目会被忽略。

    Args:
        existing: 已有的 todo 列表(可能为 None)。
        update: 本次要合并的 todo 列表(可能为 None)。

    Returns:
        合并后的 todo 列表,每个 id 在结果中唯一。
    """
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
    """合并 agent_history 并只保留最近 10 条记录,避免审计数据无限增长。

    Args:
        existing: 已有的 agent_history 列表。
        update: 本次要追加的记录列表。

    Returns:
        合并后裁剪到最近 10 条的列表。
    """
    combined = (existing or []) + (update or [])
    return combined[-10:]


def replace_if_set(existing: Any, update: Any) -> Any:
    """若 ``update`` 非 None 则使用 ``update``,否则保留 ``existing``。

    用作 LangGraph 状态 Reducer,可避免显式 None 把已有值覆盖为空。

    Args:
        existing: 已有值。
        update: 本次更新值,可能为 None。

    Returns:
        优先返回 ``update``,仅当 ``update`` 为 None 时返回 ``existing``。
    """
    return update if update is not None else existing