"""Schemas for the unpause reconciliation flow."""

from __future__ import annotations

from pydantic import BaseModel


class ReconcilePositionEntry(BaseModel):
    """A single symbol entry in the reconciliation comparison."""

    symbol: str
    master_qty: int
    master_side: str
    follower_qty: int
    follower_side: str | None
    scenario: str  # "common_same_dir" | "common_diff_dir" | "master_only"
    inferred_multiplier: float | None
    current_multiplier: float
    current_source: str  # "base" | "user_override"
    is_blacklisted: bool
    default_action: str  # "use_inferred" | "blacklist"


class ReconcileFollowerData(BaseModel):
    """Reconciliation data for a single follower."""

    follower_id: str
    follower_name: str
    base_multiplier: float
    entries: list[ReconcilePositionEntry]


class ReconcileResponse(BaseModel):
    """Response from GET /api/reconcile."""

    followers: list[ReconcileFollowerData]
    has_entries: bool


class ReconcileDecision(BaseModel):
    """A user's decision for a single symbol."""

    symbol: str
    action: str  # "use_inferred" | "manual" | "use_default"
    multiplier: float | None = None
    blacklist: bool


class ReconcileApplyFollower(BaseModel):
    """Decisions for a single follower."""

    follower_id: str
    decisions: list[ReconcileDecision]


class ReconcileApplyRequest(BaseModel):
    """Request body for POST /api/reconcile/apply."""

    followers: list[ReconcileApplyFollower]
