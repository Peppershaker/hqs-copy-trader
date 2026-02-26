"""Follower account routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.follower import Follower
from app.schemas.accounts import (
    FollowerCreate,
    FollowerResponse,
    FollowerUpdate,
    MultiplierUpdate,
)

router = APIRouter(prefix="/api/followers", tags=["followers"])


@router.get("", response_model=list[FollowerResponse])
async def list_followers(db: AsyncSession = Depends(get_db)):
    """List all follower accounts."""
    result = await db.execute(select(Follower).order_by(Follower.name))
    return result.scalars().all()


@router.post("", response_model=FollowerResponse, status_code=201)
async def create_follower(
    follower: FollowerCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a new follower account."""
    existing = await db.execute(select(Follower).where(Follower.id == follower.id))
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Follower '{follower.id}' already exists")

    obj = Follower(**follower.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


@router.get("/{follower_id}", response_model=FollowerResponse)
async def get_follower(follower_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific follower's configuration."""
    result = await db.execute(select(Follower).where(Follower.id == follower_id))
    follower = result.scalar_one_or_none()
    if not follower:
        raise HTTPException(404, "Follower not found")
    return follower


@router.put("/{follower_id}", response_model=FollowerResponse)
async def update_follower(
    follower_id: str,
    updates: FollowerUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a follower's configuration."""
    result = await db.execute(select(Follower).where(Follower.id == follower_id))
    follower = result.scalar_one_or_none()
    if not follower:
        raise HTTPException(404, "Follower not found")

    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(follower, field, value)

    await db.flush()
    await db.refresh(follower)
    return follower


@router.delete("/{follower_id}", status_code=204)
async def delete_follower(follower_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a follower account."""
    result = await db.execute(select(Follower).where(Follower.id == follower_id))
    follower = result.scalar_one_or_none()
    if not follower:
        raise HTTPException(404, "Follower not found")
    await db.delete(follower)


@router.patch("/{follower_id}/multiplier", response_model=FollowerResponse)
async def update_multiplier(
    follower_id: str,
    body: MultiplierUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a follower's base multiplier."""
    result = await db.execute(select(Follower).where(Follower.id == follower_id))
    follower = result.scalar_one_or_none()
    if not follower:
        raise HTTPException(404, "Follower not found")

    follower.base_multiplier = body.base_multiplier
    await db.flush()
    await db.refresh(follower)
    return follower


@router.patch("/{follower_id}/toggle", response_model=FollowerResponse)
async def toggle_follower(follower_id: str, db: AsyncSession = Depends(get_db)):
    """Toggle a follower's enabled/disabled state."""
    result = await db.execute(select(Follower).where(Follower.id == follower_id))
    follower = result.scalar_one_or_none()
    if not follower:
        raise HTTPException(404, "Follower not found")

    follower.enabled = not follower.enabled
    await db.flush()
    await db.refresh(follower)
    return follower
