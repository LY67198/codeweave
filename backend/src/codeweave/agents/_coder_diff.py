"""run_tools_and_diff:跑 LLM 响应里的 tool_calls + 收集 unified diff。

`_dispatch` 在函数体内 lazy import Phase 2 工具(避免 coder.py 顶层 import 整个
工具链,提速启动),并对敏感路径在工具入口拒掉。
"""
from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from codeweave.skills.security import is_sensitive_path


def run_tools_and_diff(
    llm_response: Any,
    *,
    repo_root: Path,
) -> tuple[list[dict[str, Any]], str, dict[str, bool]]:
    """执行 LLM 响应里的 tool_calls,产出 (tool_results, diff_text, writes_map)。

    Args:
        llm_response: LangChain BaseMessage 实例,含 ``.tool_calls`` 列表。
        repo_root: 仓库根目录,用于路径白名单和 diff 中的相对路径展示。

    Returns:
        三元组:
          - ``tool_results``:每个 tool_call 的执行结果 dict 列表(ok/err/path/output)。
          - ``diff_text``:对所有成功 write/edit 的文件产出的 unified diff 拼接,
            总字符数超过 8000 自动截断。
          - ``writes_map``:path → 是否成功的 dict(仅含 write/edit 调用)。
    """
    repo_root = repo_root.resolve()
    results: list[dict[str, Any]] = []
    writes: dict[str, bool] = {}

    for tc in (getattr(llm_response, "tool_calls", None) or []):
        name = tc.get("name")
        args = tc.get("args", {}) or {}
        result = _dispatch(name, args, repo_root)
        results.append(result)
        if name in {"write_file", "edit_file"}:
            writes[str(args.get("path", ""))] = result.get("ok", False)

    diff_text = _collect_diffs(writes, repo_root)
    return results, diff_text, writes


def _dispatch(name: str, args: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """分发到现有 Phase 2 工具(直接 import + call)。

    对 write/edit 工具先做路径白名单与敏感路径判定;其余工具直接透传。
    工具抛任何异常都会被捕获并以 ``ok=False`` 形式返回,避免单条工具失败炸掉整轮。

    Args:
        name: 工具名(``read_file`` / ``write_file`` / ``edit_file`` /
            ``grep_files`` / ``bash``)。
        args: 工具调用参数。
        repo_root: 仓库根目录。

    Returns:
        ``{tool, ok, ...}`` 结果 dict。
    """
    if name in {"write_file", "edit_file"}:
        path = Path(args.get("path", ""))
        try:
            path.resolve().relative_to(repo_root)
        except ValueError:
            return {"tool": name, "ok": False, "path": str(path), "err": "outside_workdir"}
        if is_sensitive_path(path):
            return {"tool": name, "ok": False, "path": str(path), "err": "sensitive_blocked"}
    try:
        if name == "read_file":
            from codeweave.tools.file_tools import read_file
            content = read_file(path=args.get("path", ""), thread_id=args.get("thread_id", "t"))
            return {"tool": name, "ok": True, "output": content[:2000]}
        if name == "write_file":
            from codeweave.tools.file_tools import write_file
            write_file(
                path=args.get("path", ""),
                content=args.get("content", ""),
                thread_id=args.get("thread_id", "t"),
            )
            return {"tool": name, "ok": True, "path": args.get("path")}
        if name == "edit_file":
            from codeweave.tools.file_tools import edit_file
            edit_file(
                path=args.get("path", ""),
                old_text=args.get("old_text", ""),
                new_text=args.get("new_text", ""),
                thread_id=args.get("thread_id", "t"),
            )
            return {"tool": name, "ok": True, "path": args.get("path")}
        if name == "grep_files":
            from codeweave.tools.file_tools import grep_files
            return {"tool": name, "ok": True, "output": grep_files(pattern=args.get("pattern", ""))}
        if name == "bash":
            from codeweave.tools.bash_tools import run_bash
            return {"tool": name, "ok": True, "output": run_bash(command=args.get("command", ""))[:1000]}
    except Exception as exc:
        return {"tool": name, "ok": False, "err": str(exc)}

    return {"tool": name, "ok": False, "err": f"unknown_tool:{name}"}


def _collect_diffs(writes: dict[str, bool], repo_root: Path) -> str:
    """对每个 write/edit 成功的文件生成 unified diff 段落(截断 8000 char)。

    Phase 5 简化:用磁盘当前内容 vs 空 before 产 diff(等价于新增),因为还没
    接入 git HEAD。Phase 7 升级为 git HEAD 对比后才会有真实 before-Content。

    Args:
        writes: ``path -> ok`` 字典。
        repo_root: 仓库根目录,用于相对路径展示。

    Returns:
        拼接后的 unified diff 字符串(可能含截断标记)。
    """
    parts: list[str] = []
    total = 0
    for path_str, ok in writes.items():
        if not ok:
            continue
        p = Path(path_str)
        try:
            after = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            rel = p.resolve().relative_to(repo_root).as_posix()
        except ValueError:
            rel = p.as_posix()
        before = ""  # Phase 7 升级为 git HEAD
        diff = "".join(difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        ))
        parts.append(diff)
        total += len(diff)
        if total > 8000:
            parts.append("\n# ... diff 截断 (Phase 7 提供完整 diff via git) ...\n")
            break
    return "\n".join(parts)


__all__ = ["run_tools_and_diff"]