"""Celery 工厂,生产 redis broker,测试可换 memory://。"""
from __future__ import annotations

from celery import Celery


def make_celery(
    *,
    app_name: str,
    broker: str,
    backend: str,
    include: list[str],
) -> Celery:
    """构造一个 Celery 实例。

    将 broker / backend 暴露为参数,便于测试时替换为 ``memory://`` 之类的
    in-process transport,无需真实 Redis。

    Args:
        app_name: Celery 应用名,通常为包名 ``"codeweave"``。
        broker: broker URL,生产用 ``redis://...``。
        backend: result backend URL。
        include: 自动 import 的 task 模块列表。

    Returns:
        已配置好 broker/backend 的 :class:`celery.Celery` 实例。
    """
    return Celery(app_name, broker=broker, backend=backend, include=include)