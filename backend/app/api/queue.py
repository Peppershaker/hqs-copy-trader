"""Queued action replay routes.

Provides endpoints for listing and replaying actions that were queued
while a follower was disconnected.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.engine.replication_engine import ReplicationEngine
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["queue"])

# Injected at startup
_get_engine: Callable[[], ReplicationEngine] | None = None


def set_queue_engine_getter(
    engine_getter: Callable[[], ReplicationEngine],
) -> None:
    global _get_engine
    _get_engine = engine_getter


class ReplayRequest(BaseModel):
    """Body for POST /api/queued-actions/{follower_id}/replay."""

    action_ids: list[str]


class DiscardRequest(BaseModel):
    """Body for POST /api/queued-actions/{follower_id}/discard."""

    action_ids: list[str]


@router.get("/queued-actions")
async def list_all_queued_actions() -> dict[str, Any]:
    """List queued actions across all followers."""
    if _get_engine is None:
        return {"error": "Not initialized"}
    engine = _get_engine()
    all_pending = engine.action_queue.get_all_pending()
    return {fid: [a.to_dict() for a in actions] for fid, actions in all_pending.items()}


@router.get("/queued-actions/{follower_id}")
async def list_queued_actions(follower_id: str) -> Any:
    """List queued actions for a specific follower."""
    if _get_engine is None:
        return {"error": "Not initialized"}
    engine = _get_engine()
    return engine.action_queue.pending_summary(follower_id)


@router.post("/queued-actions/{follower_id}/replay")
async def replay_queued_actions(
    follower_id: str, body: ReplayRequest
) -> dict[str, Any]:
    """Replay selected queued actions on a reconnected follower."""
    if _get_engine is None:
        return {"error": "Not initialized"}
    engine = _get_engine()
    result = await engine.replay_queued_actions(follower_id, body.action_ids)
    return result


@router.post("/queued-actions/{follower_id}/discard")
async def discard_queued_actions(
    follower_id: str, body: DiscardRequest
) -> dict[str, Any]:
    """Discard selected queued actions without replaying."""
    if _get_engine is None:
        return {"error": "Not initialized"}
    engine = _get_engine()
    count = await engine.discard_queued_actions(follower_id, body.action_ids)
    return {"discarded": count}
