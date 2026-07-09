"""Skill + ReviewerDecision 数据结构(spec §2.3 / §3.5)。"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class Skill(BaseModel):
    """单个 SKILL.md 文件解析后的对象(spec §2.3)。"""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    when_to_use: str = Field(default="", max_length=2000)
    priority: int = Field(default=0, ge=0, le=1000)
    body: str = Field(default="", max_length=200_000)
    parsed_sections: dict[str, str] = Field(default_factory=dict)
    path: Path | None = None  # 调试用,可空


class ReviewerDecision(BaseModel):
    """Reviewer 输出的 JSON schema(spec §3.5)。"""
    accept: bool
    score: int = Field(ge=0, le=10)
    feedback: str = Field(min_length=1, max_length=2000)
    risk_flags: list[str] = Field(default_factory=list)

    @field_validator("risk_flags")
    @classmethod
    def _normalize_risk_flags(cls, v: list[str]) -> list[str]:
        """去重 + 限长 + 全部 strip,避免 LLM 幻觉污染。"""
        seen: set[str] = set()
        out: list[str] = []
        for flag in v[:20]:  # 最多 20 个 flag
            f = str(flag).strip().lower()[:100]
            if f and f not in seen:
                seen.add(f)
                out.append(f)
        return out
