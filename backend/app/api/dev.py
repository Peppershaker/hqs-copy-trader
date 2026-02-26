"""Developer / debug routes.

Provides database reset and access to the in-memory log buffer.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.database import Base, get_engine
from app.services.log_buffer import log_buffer

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.post("/reset-db")
async def reset_database():
    """Drop all tables and recreate them.  **Destroys all data.**"""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    return {"status": "ok", "message": "Database reset complete"}


@router.get("/logs")
async def get_logs(
    source: str | None = Query(None, description="Filter: 'app' or 'das_bridge'"),
    since: int = Query(0, description="Return entries after this sequence number"),
    limit: int = Query(500, ge=1, le=5000),
):
    """Return buffered log entries from the in-memory ring buffer."""
    entries = log_buffer.get_entries(source=source, since_seq=since, limit=limit)
    return {"entries": entries, "latest_seq": log_buffer.latest_seq}


@router.delete("/logs")
async def clear_logs():
    """Clear the in-memory log buffer."""
    log_buffer.clear()
    return {"status": "ok"}
