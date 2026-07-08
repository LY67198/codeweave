"""Celery 实例(spec §6.1)。

NOTE: broker / backend 在测试中替换为 ``memory://``,避免依赖本地 Redis。
"""
from __future__ import annotations

from codeweave.config.settings import get_settings
from codeweave.tasks._compat import make_celery

_settings = get_settings()
celery_app = make_celery(
    app_name="codeweave",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=[
        "codeweave.tasks.compact",
        "codeweave.tasks.token_aggregate",
        "codeweave.tasks.cleanup",
    ],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=300,
    task_soft_time_limit=240,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)
celery_app.conf.beat_schedule = {
    "aggregate-token-usage": {
        "task": "codeweave.aggregate_token_usage",
        "schedule": float(_settings.celery_beat_aggregate_interval_seconds),
    },
    "cleanup-old-compact-results": {
        "task": "codeweave.cleanup_old_compact_results",
        "schedule": 7 * 24 * 60 * 60.0,  # 7 天一次
    },
}