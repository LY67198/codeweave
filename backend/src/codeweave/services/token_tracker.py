"""每个 LLM 调用结束写一行 token_usage(spec §7)。

失败吞异常(spec §5.3 同款态度)。成本估算用 DeepSeek v4-flash 公开价:
prompt $0.14/M, completion $0.28/M(2026-07 估算,可在 Phase 4 接 pricing API)。
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from sqlalchemy.exc import SQLAlchemyError

from codeweave.db.models import TokenUsage

logger = logging.getLogger(__name__)


# 简易 pricing($/M tokens);Phase 4 可换成查表
_PRICING: dict[str, tuple[float, float]] = {
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v4-pro": (0.55, 2.20),
}


def _estimate_cost(model: str, prompt_tok: int, completion_tok: int) -> float:
    """根据模型定价估算本次调用的成本(美元)。

    Args:
        model: 模型标识,如 ``"deepseek-v4-flash"``。
        prompt_tok: prompt token 数。
        completion_tok: completion token 数。

    Returns:
        估算成本(美元)。未知模型返回 0。
    """
    pp, cp = _PRICING.get(model, (0.0, 0.0))
    return (prompt_tok / 1_000_000) * pp + (completion_tok / 1_000_000) * cp


class _SessionFactory(Protocol):
    def __call__(self) -> Any: ...


class TokenTracker:
    """线程级 token 写入器。

    每次 LLM 调用结束调用 :meth:`track`,会在 ``token_usage`` 表新增一行,
    含 thread_id、model、prompt/completion tokens 以及按 :data:`_PRICING`
    估算的 ``cost_usd``。DB 失败时静默吞掉异常(spec §7 fail-silent)。

    Attributes:
        _factory: SQLAlchemy ``Session`` 上下文管理器工厂;默认用
            :func:`codeweave.db.base.get_session`。
    """

    def __init__(self, session_factory: _SessionFactory | None = None) -> None:
        from codeweave.db.base import get_session
        self._factory = session_factory or get_session

    def track(
        self,
        *,
        thread_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """记录一次 LLM 调用的 token 用量。

        Args:
            thread_id: 对话/线程 ID。
            model: 模型标识,例如 ``"deepseek-v4-flash"``。
            prompt_tokens: 输入 token 数。
            completion_tokens: 输出 token 数。
        """
        try:
            row = TokenUsage(
                thread_id=thread_id,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=_estimate_cost(model, prompt_tokens, completion_tokens),
            )
            with self._factory() as session:
                session.add(row)
                session.commit()
        except SQLAlchemyError as exc:
            logger.error("token_track_failed",
                         extra={"thread_id": thread_id, "error": str(exc)})