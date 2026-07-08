"""TokenTracker 单元测试(spec §7 token usage 行写入)。"""
from unittest.mock import MagicMock

import pytest

from codeweave.services.token_tracker import TokenTracker


@pytest.fixture
def fake_session_factory():
    session = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = session
    ctx.__exit__.return_value = False
    factory = MagicMock(return_value=ctx)
    return session, factory


def test_track_records_one_row(fake_session_factory):
    session, factory = fake_session_factory
    tracker = TokenTracker(factory)

    tracker.track(thread_id="t-1", model="deepseek-v4-flash",
                  prompt_tokens=120, completion_tokens=80)

    session.add.assert_called_once()
    row = session.add.call_args[0][0]
    assert row.thread_id == "t-1"
    assert row.model == "deepseek-v4-flash"
    assert row.prompt_tokens == 120
    assert row.completion_tokens == 80
    assert float(row.cost_usd) >= 0


def test_track_swallows_db_error(fake_session_factory):
    from sqlalchemy.exc import OperationalError
    session, factory = fake_session_factory
    session.commit.side_effect = OperationalError("stmt", {}, Exception("x"))
    tracker = TokenTracker(factory)
    tracker.track(thread_id="t-1", model="m", prompt_tokens=1, completion_tokens=1)
    # 不抛异常