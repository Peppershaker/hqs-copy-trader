"""Short sale task management routes.

Provides endpoints for listing and cancelling on-demand short sale tasks
(locate-then-short workflows managed by :class:`ShortSaleManager`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter

from app.engine.replication_engine import ReplicationEngine

router = APIRouter(prefix="/api/short-sales", tags=["short-sales"])

# Injected at startup
_get_engine: Callable[[], ReplicationEngine] | None = None


def set_engine_getter(
    engine_getter: Callable[[], ReplicationEngine],
) -> None:
    """Inject the engine getter used by short-sales endpoints."""
    global _get_engine
    _get_engine = engine_getter


@router.get("/tasks")
async def list_short_sale_tasks() -> list[dict[str, Any]]:
    """List all active short sale tasks across all followers."""
    if _get_engine is None:
        return []
    engine = _get_engine()
    return engine.short_sale_manager.get_active_tasks()


@router.get("/tasks/all")
async def list_all_short_sale_tasks() -> list[dict[str, Any]]:
    """List all short sale tasks (including completed/failed/cancelled)."""
    if _get_engine is None:
        return []
    engine = _get_engine()
    return engine.short_sale_manager.get_all_tasks()


@router.post("/tasks/{task_id}/cancel")
async def cancel_short_sale_task(task_id: str) -> dict[str, Any]:
    """Cancel a specific short sale task."""
    if _get_engine is None:
        return {"success": False, "error": "Not initialized"}
    engine = _get_engine()
    cancelled = await engine.short_sale_manager.cancel_task(task_id)
    return {"success": cancelled, "task_id": task_id}
