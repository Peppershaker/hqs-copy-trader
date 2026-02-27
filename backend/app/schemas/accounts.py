"""Account-related Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# --- Master ---


class MasterConfigCreate(BaseModel):
    """Request schema for creating a master account configuration."""

    broker_id: str
    host: str
    port: int = Field(ge=1, le=65535)
    username: str
    password: str
    account_id: str
    locate_routes: dict[str, int] | None = None


class MasterConfigResponse(BaseModel):
    """Response schema for a master account configuration."""

    id: int
    broker_id: str
    host: str
    port: int
    username: str
    account_id: str
    locate_routes: dict[str, int] | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Follower ---


class FollowerCreate(BaseModel):
    """Request schema for creating a follower account."""

    id: str = Field(
        min_length=1, description="Unique follower identifier (e.g., 'acct-cobra-2')"
    )
    name: str = Field(min_length=1, description="Display name")
    broker_id: str
    host: str
    port: int = Field(ge=1, le=65535)
    username: str
    password: str
    account_id: str
    base_multiplier: float = Field(default=1.0, gt=0)
    max_locate_price_delta: float = Field(default=0.01, ge=0)
    locate_retry_timeout: int = Field(default=300, ge=0)
    auto_accept_locates: bool = False
    enabled: bool = True
    locate_routes: dict[str, int] | None = None


class FollowerUpdate(BaseModel):
    """Request schema for updating a follower account."""

    name: str | None = None
    broker_id: str | None = None
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    account_id: str | None = None
    base_multiplier: float | None = Field(default=None, gt=0)
    max_locate_price_delta: float | None = Field(default=None, ge=0)
    locate_retry_timeout: int | None = Field(default=None, ge=0)
    auto_accept_locates: bool | None = None
    enabled: bool | None = None
    locate_routes: dict[str, int] | None = None


class FollowerResponse(BaseModel):
    """Response schema for a follower account."""

    id: str
    name: str
    broker_id: str
    host: str
    port: int
    username: str
    account_id: str
    base_multiplier: float
    max_locate_price_delta: float
    locate_retry_timeout: int
    auto_accept_locates: bool
    enabled: bool
    locate_routes: dict[str, int] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MultiplierUpdate(BaseModel):
    """Request schema for updating a follower's base multiplier."""

    base_multiplier: float = Field(gt=0)
