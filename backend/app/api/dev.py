"""Developer / debug routes.

Provides database reset, in-memory log buffer, and log directory management.
"""

from __future__ import annotations

import pathlib
import shutil

from fastapi import APIRouter, HTTPException, Query

from app.database import Base, get_engine
from app.services.log_buffer import log_buffer

_LOG_BASE = pathlib.Path(__file__).resolve().parent.parent.parent / "logs"

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


def _dir_size(path: pathlib.Path) -> int:
    """Total bytes of all files in a directory (non-recursive)."""
    return sum(f.stat().st_size for f in path.iterdir() if f.is_file())


@router.get("/log-dirs")
async def list_log_dirs():
    """List all log run directories with their sizes."""
    if not _LOG_BASE.is_dir():
        return {"directories": []}
    dirs = sorted(
        (d for d in _LOG_BASE.iterdir() if d.is_dir()),
        key=lambda d: d.name,
        reverse=True,
    )
    return {
        "directories": [
            {
                "name": d.name,
                "files": [f.name for f in sorted(d.iterdir()) if f.is_file()],
                "size_bytes": _dir_size(d),
            }
            for d in dirs
        ],
    }


@router.post("/log-dirs/delete")
async def delete_log_dirs(body: dict):
    """Delete one or more log run directories by name."""
    names: list[str] = body.get("names", [])
    if not names:
        raise HTTPException(400, "No directory names provided")

    deleted: list[str] = []
    for name in names:
        target = _LOG_BASE / name
        # Prevent path traversal
        if not target.resolve().parent == _LOG_BASE.resolve():
            continue
        if target.is_dir():
            shutil.rmtree(target)
            deleted.append(name)

    return {"deleted": deleted}
