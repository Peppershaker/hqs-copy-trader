"""Blacklist-related Pydantic schemas."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, field_validator

_TICKER_RE = re.compile(r"^[A-Za-z]{1,5}$")


class BlacklistEntryCreate(BaseModel):
    follower_id: str
    symbol: str
    reason: str | None = "manual"

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        v = v.strip().upper()
        if not _TICKER_RE.match(v):
            raise ValueError("Symbol must be 1-5 letters only")
        return v


class BlacklistEntryResponse(BaseModel):
    id: int
    follower_id: str
    symbol: str
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
