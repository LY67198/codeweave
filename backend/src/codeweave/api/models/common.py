"""跨模型用的辅助类型。"""
from __future__ import annotations

from pydantic import BaseModel


class CursorOut(BaseModel):
    """分页 cursor 输出(Phase 4 单页够用,留扩展位)。"""
    limit: int = 100
    next_cursor: str | None = None
