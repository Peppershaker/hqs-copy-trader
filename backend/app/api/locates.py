"""Locate action routes (accept / reject prompts)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.engine.replication_engine import ReplicationEngine
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/locates", tags=["locates"])

# The engine is injected at app startup via app.state
_get_engine: Callable[[], ReplicationEngine] | None = None


def set_engine_getter(getter: Callable[[], ReplicationEngine]) -> None:
    """Called at app startup to inject the engine reference."""
    global _get_engine
    _get_engine = getter


def _engine() -> ReplicationEngine:
    if _get_engine is None:
        raise HTTPException(503, "Engine not initialized")
    return _get_engine()


@router.post("/{locate_map_id}/accept")
async def accept_locate(locate_map_id: int) -> dict[str, Any]:
    """Accept a prompted locate offer."""
    engine = _engine()
    result = await engine.locate_replicator.handle_user_accept(locate_map_id)
    if not result.get("success"):
        raise HTTPException(404, result.get("error", "Failed to accept"))
    return result


@router.post("/{locate_map_id}/reject")
async def reject_locate(locate_map_id: int) -> dict[str, Any]:
    """Reject a prompted locate offer (auto-blacklists the symbol)."""
    engine = _engine()
    result = await engine.locate_replicator.handle_user_reject(locate_map_id)
    if not result.get("success"):
        raise HTTPException(404, result.get("error", "Failed to reject"))
    return result
