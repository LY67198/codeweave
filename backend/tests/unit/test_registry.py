"""ToolRegistry 单元测试。"""
from __future__ import annotations

from langchain_core.tools import BaseTool

from codeweave.tools.registry import ToolMeta, ToolRegistry, register, registry


def test_registry_is_singleton():
    """registry 模块级实例应该是单例。"""
    assert isinstance(registry, ToolRegistry)


def test_register_returns_decorator_with_metadata():
    """@register 应该把工具登记到 registry 并保留原函数。"""
    reg = ToolRegistry()

    @reg.register(name="demo", plan_mode_safe=True, requires_permission=False, category="file")
    def demo(x: int) -> str:
        """Demo tool."""
        return str(x)

    meta = reg.get_meta("demo")
    assert isinstance(meta, ToolMeta)
    assert isinstance(meta.tool, BaseTool)
    assert meta.plan_mode_safe is True
    assert meta.requires_permission is False
    assert meta.category == "file"
    # 原函数保留
    assert demo(42) == "42"


def test_module_level_register_decorator():
    """模块级 register 装饰器工作正常。"""
    from codeweave.tools import registry as global_registry

    # 防止污染:用完即清
    @register(name="_tmp_global", plan_mode_safe=False, requires_permission=True, category="bash")
    def _tmp(cmd: str) -> str:
        return cmd

    try:
        meta = global_registry.get_meta("_tmp_global")
        assert meta.requires_permission is True
        assert meta.category == "bash"
    finally:
        global_registry.clear()


def test_get_tools_for_mode_plan_filters_safely():
    """plan 模式只返回 plan_mode_safe=True 的工具。"""
    reg = ToolRegistry()

    @reg.register(name="safe_tool", plan_mode_safe=True, requires_permission=False, category="file")
    def safe_tool() -> str:
        """Safe."""
        return "safe"

    @reg.register(name="unsafe_tool", plan_mode_safe=False, requires_permission=False, category="file")
    def unsafe_tool() -> str:
        """Unsafe."""
        return "unsafe"

    plan_tools = reg.get_tools_for_mode("plan")
    tool_names = {t.name for t in plan_tools}
    assert "safe_tool" in tool_names
    assert "unsafe_tool" not in tool_names

    exec_tools = reg.get_tools_for_mode("execute")
    exec_names = {t.name for t in exec_tools}
    assert "safe_tool" in exec_names
    assert "unsafe_tool" in exec_names

    reg.clear()


def test_clear_resets_registry():
    """clear() 应该清空所有已注册工具。"""
    reg = ToolRegistry()

    @reg.register(name="x", plan_mode_safe=True, requires_permission=False, category="file")
    def x() -> str:
        return "x"

    assert reg.get_meta("x") is not None
    reg.clear()
    import pytest
    with pytest.raises(KeyError):
        reg.get_meta("x")