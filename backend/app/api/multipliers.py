"""Symbol multiplier override routes."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.symbol_multiplier import SymbolMultiplier
from app.schemas.multipliers import SymbolMultiplierResponse, SymbolMultiplierUpdate

_TICKER_RE = re.compile(r"^[A-Za-z]{1,5}$")

router = APIRouter(prefix="/api/multipliers", tags=["multipliers"])


@router.get("/{follower_id}", response_model=list[SymbolMultiplierResponse])
async def get_multipliers(
    follower_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all symbol multiplier overrides for a follower."""
    result = await db.execute(
        select(SymbolMultiplier)
        .where(SymbolMultiplier.follower_id == follower_id)
        .order_by(SymbolMultiplier.symbol)
    )
    return result.scalars().all()


@router.put(
    "/{follower_id}/{symbol}",
    response_model=SymbolMultiplierResponse,
)
async def set_multiplier(
    follower_id: str,
    symbol: str,
    body: SymbolMultiplierUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Set or update a per-symbol multiplier override."""
    symbol = symbol.strip().upper()
    if not _TICKER_RE.match(symbol):
        raise HTTPException(422, "Symbol must be 1-5 letters only")
    result = await db.execute(
        select(SymbolMultiplier).where(
            SymbolMultiplier.follower_id == follower_id,
            SymbolMultiplier.symbol == symbol,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.multiplier = body.multiplier
        existing.source = "user_override"
        await db.flush()
        await db.refresh(existing)
        return existing
    else:
        obj = SymbolMultiplier(
            follower_id=follower_id,
            symbol=symbol,
            multiplier=body.multiplier,
            source="user_override",
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj


@router.delete("/{follower_id}/{symbol}", status_code=204)
async def remove_multiplier(
    follower_id: str,
    symbol: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove a per-symbol multiplier override (revert to base multiplier)."""
    symbol = symbol.strip().upper()
    if not _TICKER_RE.match(symbol):
        raise HTTPException(422, "Symbol must be 1-5 letters only")
    result = await db.execute(
        select(SymbolMultiplier).where(
            SymbolMultiplier.follower_id == follower_id,
            SymbolMultiplier.symbol == symbol,
        )
    )
    existing = result.scalar_one_or_none()
    if not existing:
        raise HTTPException(404, "Symbol multiplier override not found")
    await db.delete(existing)
