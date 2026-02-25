"""Order replication Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OrderReplicationResponse(BaseModel):
    id: int
    master_order_token: int
    master_order_id: int | None
    follower_id: str
    follower_order_token: int
    follower_order_id: int | None
    symbol: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
