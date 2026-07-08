"""Tool Registry — 工具注册中心。

提供 ``@register`` 装饰器将 LangChain 工具登记到 ``ToolRegistry`` 单例,
并支持按 ``plan_mode`` / ``execute`` 模式过滤。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from langchain_core.tools import BaseTool, tool


@dataclass(frozen=True)
class ToolMeta:
    """已注册工具的元数据。

    Attributes:
        tool: LangChain BaseTool 实例。
        plan_mode_safe: 是否在 Plan Mode 下可用(只读工具为 True)。
        requires_permission: 是否需要用户批准(危险命令类工具为 True)。
        category: 工具分类,便于按类别过滤。
    """

    tool: BaseTool
    plan_mode_safe: bool
    requires_permission: bool
    category: str


class ToolRegistry:
    """工具注册中心。

    用法::

        registry = ToolRegistry()

        @registry.register(name="x", plan_mode_safe=True, ...)
        def x() -> str: ...

        tools = registry.get_tools_for_mode("plan")
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolMeta] = {}

    def register(
        self,
        *,
        name: str,
        plan_mode_safe: bool,
        requires_permission: bool,
        category: str,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """装饰器:登记一个函数为工具。

        Args:
            name: 工具名(显式传入,避免改函数名意外重命名)。
            plan_mode_safe: Plan Mode 是否可用。
            requires_permission: 是否需要用户批准。
            category: 工具分类("file" / "bash" / "todo" / "skill" / "subagent" / "compact")。

        Returns:
            装饰器函数,保留原函数引用以便直接调用(主要用于测试)。
        """

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            # 使用 fn 的 docstring 作为 tool description,若无则用 name 占位
            # 避免 LangChain @tool 在缺失 docstring 时抛 ValueError
            description = fn.__doc__ or f"Tool: {name}"
            base_tool = tool(fn, description=description)
            # 强制 tool.name 与登记名一致(防止 @tool 默认用函数名覆盖)
            base_tool.name = name
            self._tools[name] = ToolMeta(
                tool=base_tool,
                plan_mode_safe=plan_mode_safe,
                requires_permission=requires_permission,
                category=category,
            )
            return fn

        return decorator

    def get_tools_for_mode(self, mode: Literal["plan", "execute"]) -> list[BaseTool]:
        """按模式返回工具列表。

        Args:
            mode: ``"plan"`` 只返 plan_mode_safe=True;``"execute"`` 返回全部。

        Returns:
            工具列表(顺序与登记顺序一致)。
        """
        if mode == "plan":
            return [m.tool for m in self._tools.values() if m.plan_mode_safe]
        return [m.tool for m in self._tools.values()]

    def get_meta(self, name: str) -> ToolMeta:
        """按名取元数据。

        Args:
            name: 工具名。

        Returns:
            对应的 ToolMeta。

        Raises:
            KeyError: 工具未登记。
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not registered")
        return self._tools[name]

    def clear(self) -> None:
        """清空所有登记(仅供测试使用)。"""
        self._tools.clear()


# 模块级单例,所有工具 import 时向此实例注册
registry = ToolRegistry()


def register(
    *,
    name: str,
    plan_mode_safe: bool,
    requires_permission: bool,
    category: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """模块级 register 装饰器快捷方式(默认注册到全局 registry)。"""
    return registry.register(
        name=name,
        plan_mode_safe=plan_mode_safe,
        requires_permission=requires_permission,
        category=category,
    )