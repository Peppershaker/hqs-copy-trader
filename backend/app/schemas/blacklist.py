"""Blacklist-related Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BlacklistEntryCreate(BaseModel):
    follower_id: str
    symbol: str
    reason: str | None = "manual"


class BlacklistEntryResponse(BaseModel):
    id: int
    follower_id: str
    symbol: str
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
