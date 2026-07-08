"""用真 DeepSeek v4-flash 跑一次完整 compact 闭环。

跑前需要:
    - 本地 .env 有 OPENAI_API_KEY(DeepSeek / Qwen / GLM 等 OpenAI 兼容服务)
    - 本地 Postgres 可达(``DATABASE_URL`` + docker compose up)

默认 skip:加 ``-m llm`` 才跑,避免 CI / 普通 dev 误触发真实 LLM 调用。
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.exc import DBAPIError, OperationalError

from codeweave.agents._compact_check import decide_compact_action
from codeweave.config.settings import get_settings
from codeweave.db.base import SessionLocal
from codeweave.db.models import CompactResult


def _postgres_reachable(url: str, timeout: float = 2.0) -> bool:
    """短超时探测 Postgres 是否可达,避免测试集卡死。"""
    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(
            url,
            connect_args={"connect_timeout": int(timeout)},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (OperationalError, DBAPIError, OSError, ValueError):
        return False


@pytest.fixture(autouse=True)
def require_postgres():
    """若没有可用的 postgres 则跳过整个 e2e。"""
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url:
        pytest.skip("DATABASE_URL not set to a postgres URL")
    if not _postgres_reachable(url):
        pytest.skip(f"Postgres not reachable at {url}")


@pytest.fixture(autouse=True)
def require_openai_key():
    """若没有真实的 OPENAI_API_KEY 则跳过,避免 dummy key 让 langchain 报 401。"""
    key = os.environ.get("OPENAI_API_KEY", "")
    base = os.environ.get("OPENAI_BASE_URL", "")
    # conftest 默认 set 了 "sk-test" 占位,这里判断是否为真 key
    if not key or key == "sk-test" or "example.invalid" in base:
        pytest.skip(
            "OPENAI_API_KEY / OPENAI_BASE_URL not configured for real LLM "
            "(conftest 占位,跳过)"
        )


@pytest.fixture(autouse=True)
def celery_eager():
    """让 Celery 在当前进程同步执行,免去真实 broker。

    进入时打开 ``task_always_eager``,退出时还原,避免污染其他测试。
    """
    from codeweave.tasks.celery_app import celery_app

    prev = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    try:
        yield celery_app
    finally:
        celery_app.conf.task_always_eager = prev


@pytest.mark.llm
def test_real_compact_roundtrip_deepseek():
    """dispatch → apply 完整闭环,中间真走 DeepSeek 摘要。"""
    settings = get_settings()
    # 把阈值临时调极低,确保触发
    assert settings.compact_threshold > 0
    tid = "real-llm-smoke-1"

    # 清旧数据,避免历史脏行干扰 partial unique index
    with SessionLocal() as session:
        session.query(CompactResult).filter_by(thread_id=tid).delete()
        session.commit()

    # 多条 HumanMessage(30 条,每条约 100 token),让 choose_compact_range 真的
    # 有中间区可压缩 — 单条消息下 keep_last_n=6 > len 会让中间区为空,
    # compact 任务提前返回 nothing_to_compact,无法验证 LLM 摘要闭环。
    long_content = ("CodeWeave 是一个 LangGraph 多 Agent 编码助手。 "
                    "它包含 supervisor / explorer / coder / reviewer / "
                    "executor / compact 五个核心 Agent 节点,"
                    "由 supervisor 协调探索、编码、审阅、执行、压缩"
                    "多个工作环节,像织机编织代码一样协作。" * 30)
    state = {
        "messages": [HumanMessage(content=long_content) for _ in range(30)],
        "thread_id": tid,
    }

    dispatched = {}

    def fake_dispatch(thread_id: str) -> str:
        """fake dispatch 回调:同步跑 task body,真 LLM 真 Postgres。"""
        with patch("codeweave.tasks.compact._get_checkpointer") as ck:
            # _get_checkpointer() → ck with get_tuple() (PostgresSaver 直 API,
            # 不是 CompiledStateGraph 的 get_state)
            ck.return_value.get_tuple.return_value.checkpoint = {
                "channel_values": {"messages": state["messages"]},
            }
            from codeweave.tasks.compact import compact_thread as task_fn

            row_id = task_fn.apply(args=[thread_id]).get()
            dispatched["id"] = row_id
            return row_id

    # 1) 第一轮:dispatch(超阈值 → 触发 Celery)
    action1 = decide_compact_action(
        state, threshold=10, enabled=True, session_factory=SessionLocal,
        dispatch_fn=fake_dispatch, thread_id_getter=lambda s: tid,
    )
    # fake_dispatch 通过 celery eager 同步执行,此时 DB 已有 status=done 行
    assert action1.kind == "dispatch", f"expected dispatch, got {action1.kind}"
    assert action1.compact_id
    assert dispatched["id"] == action1.compact_id

    # 验证 DB 已经写入一条 status=done 的行
    with SessionLocal() as session:
        rows = session.query(CompactResult).filter_by(thread_id=tid).all()
        done_rows = [r for r in rows if r.status == "done"]
        assert len(done_rows) >= 1, f"expected done row, got {[(r.status, r.error) for r in rows]}"
        done_row = done_rows[0]
        # summary_message 由真 LLM 写入,content 必须非空
        assert done_row.summary_message is not None
        assert isinstance(done_row.summary_message, dict)
        assert done_row.summary_message.get("content"), (
            f"summary content empty: {done_row.summary_message}"
        )

    # 2) 第二轮:apply 路径,summary 替换进 messages
    state_next = {**state, "messages": state["messages"]}
    action2 = decide_compact_action(
        state_next, threshold=10, enabled=True, session_factory=SessionLocal,
        dispatch_fn=fake_dispatch, thread_id_getter=lambda s: tid,
    )
    assert action2.kind == "executor"
    assert action2.new_messages is not None
    # new_messages 中必须包含一条非空的 AIMessage(summary 来自真 LLM)
    assert any(
        isinstance(m, AIMessage) and getattr(m, "content", "") != ""
        for m in action2.new_messages
    ), f"no AIMessage with content in {action2.new_messages}"

    # apply 之后 DB 中该行应该已被标 applied=True
    with SessionLocal() as session:
        rows = session.query(CompactResult).filter_by(thread_id=tid).all()
        assert any(r.applied is True for r in rows), (
            f"no applied=True row in {[(r.status, r.applied) for r in rows]}"
        )

    # 清理:测试结束把 thread_id 关联的 CompactResult 全部删掉,避免污染
    with SessionLocal() as session:
        session.query(CompactResult).filter_by(thread_id=tid).delete()
        session.commit()