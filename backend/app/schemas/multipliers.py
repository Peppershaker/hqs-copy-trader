"""Multiplier-related Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SymbolMultiplierUpdate(BaseModel):
    multiplier: float = Field(gt=0)


class SymbolMultiplierResponse(BaseModel):
    id: int
    follower_id: str
    symbol: str
    multiplier: float
    source: str
    updated_at: datetime

    model_config = {"from_attributes": True}
