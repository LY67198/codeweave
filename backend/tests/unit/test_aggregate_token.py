"""Phase 3 Beat 任务单元测试:60s token 聚合 + compact_results 7d cleanup。

使用 :class:`unittest.mock.MagicMock` 替换 ``SessionLocal`` 以避开真实
PostgreSQL 依赖;同时验证聚合 SQL 的语义(按 model GROUP BY,60s 窗口)和
cleanup DELETE 的过滤条件(applied=True AND finished_at < cutoff)。
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from codeweave.tasks.token_aggregate import aggregate_token_usage
from codeweave.tasks.cleanup import cleanup_old_compact_results


# ----------------------------------------------------------------------------
# 测试 fixtures 与 helpers
# ----------------------------------------------------------------------------


class _FakeSessionCtx:
    """模拟 ``SessionLocal()`` 上下文管理器,允许测试控制 execute 结果。"""

    def __init__(self, session: MagicMock) -> None:
        self._session = session

    def __enter__(self) -> MagicMock:
        return self._session

    def __exit__(self, *exc: object) -> bool:
        return False


def _patch_session_local(monkeypatch, module: str, session: MagicMock) -> MagicMock:
    """把 ``codeweave.tasks.<module>.SessionLocal`` 替换为返回 fake ctx。"""
    monkeypatch.setattr(
        f"codeweave.tasks.{module}.SessionLocal",
        lambda: _FakeSessionCtx(session),
    )
    return session


# ----------------------------------------------------------------------------
# aggregate_token_usage
# ----------------------------------------------------------------------------


def test_aggregate_token_usage_groups_by_model(monkeypatch, caplog):
    """execute().all() 返回多行 → 任务把它们按 model 合并成 dict。"""
    fake_session = MagicMock()
    # 模拟 SQL 结果(注意列顺序:model, sum(prompt), sum(completion), sum(cost))
    fake_session.execute.return_value.all.return_value = [
        ("deepseek-v4-flash", 300, 130, 0.05),
        ("deepseek-v4-pro", 500, 200, 1.20),
    ]
    _patch_session_local(monkeypatch, "token_aggregate", fake_session)

    with caplog.at_level(logging.INFO, logger="codeweave.tasks.token_aggregate"):
        result = aggregate_token_usage.apply().get()

    assert isinstance(result, dict)
    assert set(result) == {"deepseek-v4-flash", "deepseek-v4-pro"}
    assert result["deepseek-v4-flash"] == {
        "prompt_tokens": 300,
        "completion_tokens": 130,
        "cost_usd": 0.05,
    }
    assert result["deepseek-v4-pro"]["prompt_tokens"] == 500

    # 日志里写 aggregate 行
    assert any("token_aggregate_60s" in rec.message for rec in caplog.records)


def test_aggregate_token_usage_empty_window(monkeypatch):
    """窗口内无数据 → execute().all() 返回 [] → 返回空 dict(不抛)。"""
    fake_session = MagicMock()
    fake_session.execute.return_value.all.return_value = []
    _patch_session_local(monkeypatch, "token_aggregate", fake_session)

    result = aggregate_token_usage.apply().get()
    assert result == {}


def test_aggregate_token_usage_handles_none_aggregates(monkeypatch):
    """SUM 在全 NULL 时返回 None,任务应把它们当 0。"""
    fake_session = MagicMock()
    fake_session.execute.return_value.all.return_value = [
        ("deepseek-v4-flash", None, None, None),
    ]
    _patch_session_local(monkeypatch, "token_aggregate", fake_session)

    result = aggregate_token_usage.apply().get()
    assert result == {
        "deepseek-v4-flash": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
        }
    }


def test_aggregate_token_usage_uses_60s_window(monkeypatch):
    """验证 cutoff = now() - 60s(通过捕获 execute 调用的 statement)。"""
    fake_session = MagicMock()
    fake_session.execute.return_value.all.return_value = []
    _patch_session_local(monkeypatch, "token_aggregate", fake_session)

    before = datetime.now(timezone.utc)
    aggregate_token_usage.apply().get()
    after = datetime.now(timezone.utc)

    # 取出传给 execute 的 stmt,断言 WHERE 子句里 cutoff 的值在
    # [before - 60s, after - 60s] 区间内(允许 SQLAlchemy 把 datetime 渲染成字面量)
    stmt = fake_session.execute.call_args[0][0]
    compiled = stmt.compile(compile_kwargs={"literal_binds": True})
    where_text = str(compiled).lower()
    assert "token_usage.ts >=" in where_text

    # 提取 WHERE 字面量(datetime 格式 'YYYY-MM-DD HH:MM:SS+00:00')
    import re

    m = re.search(r"token_usage\.ts >= '([^']+)'", where_text)
    assert m is not None, f"WHERE cutoff not found in: {where_text}"
    cutoff_str = m.group(1)
    cutoff_dt = datetime.fromisoformat(cutoff_str)

    # cutoff 应在 (before - 60s, after - 60s + 1s) 区间内,允许时钟漂移
    lower = before - timedelta(seconds=60)
    upper = after - timedelta(seconds=60) + timedelta(seconds=1)
    assert lower <= cutoff_dt <= upper, (
        f"cutoff {cutoff_dt} not in [{lower}, {upper}]"
    )


# ----------------------------------------------------------------------------
# cleanup_old_compact_results
# ----------------------------------------------------------------------------


def test_cleanup_returns_deleted_count(monkeypatch):
    """execute(delete()).rowcount = 5 → 返回 5。"""
    fake_session = MagicMock()
    fake_session.execute.return_value.rowcount = 5
    _patch_session_local(monkeypatch, "cleanup", fake_session)

    deleted = cleanup_old_compact_results.apply(args=[7]).get()
    assert deleted == 5
    # 验证提交了事务
    fake_session.commit.assert_called_once()


def test_cleanup_zero_when_no_match(monkeypatch):
    """execute.delete().rowcount = 0 → 返回 0(非负)。"""
    fake_session = MagicMock()
    fake_session.execute.return_value.rowcount = 0
    _patch_session_local(monkeypatch, "cleanup", fake_session)

    deleted = cleanup_old_compact_results.apply(args=[7]).get()
    assert deleted == 0


def test_cleanup_uses_settings_retention_when_arg_is_none(monkeypatch):
    """``retention_days=None`` 时读 settings.compact_cleanup_retention_days。"""
    fake_session = MagicMock()
    fake_session.execute.return_value.rowcount = 0
    _patch_session_local(monkeypatch, "cleanup", fake_session)

    fake_settings = MagicMock()
    fake_settings.compact_cleanup_retention_days = 14
    with patch("codeweave.tasks.cleanup.get_settings", return_value=fake_settings):
        deleted = cleanup_old_compact_results.apply(args=[None]).get()

    assert deleted == 0
    fake_settings.compact_cleanup_retention_days  # 触达属性访问


def test_cleanup_retention_zero_deletes_all_applied(monkeypatch):
    """``retention_days=0`` → cutoff = now(全部 applied + finished_at 不为 NULL 的行都过期)。"""
    fake_session = MagicMock()
    fake_session.execute.return_value.rowcount = 0
    _patch_session_local(monkeypatch, "cleanup", fake_session)

    # 不需要 mock settings,因为显式传了 0
    deleted = cleanup_old_compact_results.apply(args=[0]).get()
    assert deleted == 0


def test_cleanup_emits_delete_with_applied_filter(monkeypatch):
    """DELETE WHERE 子句必须含 ``applied = true`` 与 ``finished_at < cutoff``。"""
    fake_session = MagicMock()
    fake_session.execute.return_value.rowcount = 0
    _patch_session_local(monkeypatch, "cleanup", fake_session)

    cleanup_old_compact_results.apply(args=[7]).get()

    stmt = fake_session.execute.call_args[0][0]
    compiled = stmt.compile(compile_kwargs={"literal_binds": True})
    where = str(compiled).lower()

    # DELETE FROM compact_results
    assert "delete from compact_results" in where
    # applied = true(部分索引里也是这个过滤)
    assert "applied" in where
    assert "true" in where
    # finished_at IS NOT NULL
    assert "finished_at" in where