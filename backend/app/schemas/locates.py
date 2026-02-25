"""Locate replication Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LocateMapResponse(BaseModel):
    id: int
    master_locate_id: int | None
    follower_id: str
    symbol: str
    master_qty: int
    target_qty: int
    master_price: float | None
    follower_price: float | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LocateActionRequest(BaseModel):
    """Used for accept/reject actions on a locate prompt."""

    pass  # No body needed — action is in the URL path
