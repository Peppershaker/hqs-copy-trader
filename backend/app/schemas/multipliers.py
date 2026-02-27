"""Multiplier-related Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SymbolMultiplierUpdate(BaseModel):
    """Request schema for updating a symbol-specific multiplier."""

    multiplier: float = Field(gt=0)


class SymbolMultiplierResponse(BaseModel):
    """Response schema for a symbol-specific multiplier."""

    id: int
    follower_id: str
    symbol: str
    multiplier: float
    source: str
    updated_at: datetime

    model_config = {"from_attributes": True}
