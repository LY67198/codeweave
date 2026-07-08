"""CodeWeave 工具包。

通过 import 各子模块触发 @register 装饰器,把工具登记到全局 registry。
"""
from __future__ import annotations

from typing import Literal

from langchain_core.tools import BaseTool

from codeweave.tools.registry import ToolMeta, ToolRegistry, register, registry


def get_tools_for_mode(mode: Literal["plan", "execute"]) -> list[BaseTool]:
    """便捷函数:按模式返回工具列表。

    Args:
        mode: ``"plan"`` 只返 plan_mode_safe=True;``"execute"`` 返回全部。

    Returns:
        工具列表(BaseTool 实例)。
    """
    return registry.get_tools_for_mode(mode)


__all__ = [
    "ToolMeta",
    "ToolRegistry",
    "register",
    "registry",
    "get_tools_for_mode",
]


# 触发子模块 import(让 @register 装饰器执行)
# 注意:导入必须放在 __all__ 之后以避免循环引用
from codeweave.tools import bash_tools  # noqa: E402, F401
from codeweave.tools import file_tools  # noqa: E402, F401
from codeweave.tools import todo_tools  # noqa: E402, F401