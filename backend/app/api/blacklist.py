"""Blacklist management routes."""

from __future__ import annotations

from app.database import get_db
from app.models.blacklist import BlacklistEntry
from app.schemas.blacklist import BlacklistEntryCreate, BlacklistEntryResponse
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/blacklist", tags=["blacklist"])


@router.get("", response_model=list[BlacklistEntryResponse])
async def list_blacklist(
    follower_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List blacklist entries, optionally filtered by follower."""
    query = select(BlacklistEntry).order_by(
        BlacklistEntry.follower_id, BlacklistEntry.symbol
    )
    if follower_id:
        query = query.where(BlacklistEntry.follower_id == follower_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=BlacklistEntryResponse, status_code=201)
async def add_blacklist(
    entry: BlacklistEntryCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a symbol to the blacklist for a follower."""
    # Check for duplicate
    result = await db.execute(
        select(BlacklistEntry).where(
            BlacklistEntry.follower_id == entry.follower_id,
            BlacklistEntry.symbol == entry.symbol.upper(),
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(409, "Symbol already blacklisted for this follower")

    obj = BlacklistEntry(
        follower_id=entry.follower_id,
        symbol=entry.symbol.upper(),
        reason=entry.reason,
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


@router.delete("/{entry_id}", status_code=204)
async def remove_blacklist(entry_id: int, db: AsyncSession = Depends(get_db)):
    """Remove a blacklist entry by ID."""
    result = await db.execute(
        select(BlacklistEntry).where(BlacklistEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Blacklist entry not found")
    await db.delete(entry)
