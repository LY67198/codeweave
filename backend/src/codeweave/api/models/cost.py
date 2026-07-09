"""token 用量聚合模型(spec §2.3)。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CostEntry(BaseModel):
    """单模型聚合行。"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


class CostByModel(BaseModel):
    """GET /cost 响应 — 按模型聚合一段时间窗口的 token 用量。"""
    since: datetime = Field(..., description="窗口起点(目前为最近 60s,beat 任务聚合)")
    by_model: dict[str, CostEntry] = Field(default_factory=dict)
