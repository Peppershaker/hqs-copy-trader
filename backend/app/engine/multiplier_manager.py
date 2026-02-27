"""Multiplier manager.

Resolves the effective position size multiplier for a given follower + symbol.

Resolution order:
  1. Per-symbol user override (highest priority)
  2. Per-symbol auto-inferred from position sizes
  3. Follower base multiplier (default fallback)
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.database import get_session_factory
from app.models.follower import Follower
from app.models.symbol_multiplier import SymbolMultiplier

logger = logging.getLogger(__name__)


class MultiplierManager:
    """Resolves effective multiplier per follower per symbol."""

    def __init__(self) -> None:
        """Initialize empty in-memory multiplier caches."""
        # In-memory caches for fast access (hot path during replication)
        self._base_multipliers: dict[str, float] = {}  # follower_id → base
        self._symbol_overrides: dict[
            tuple[str, str], float
        ] = {}  # (follower_id, symbol) → mult
        self._symbol_sources: dict[
            tuple[str, str], str
        ] = {}  # (follower_id, symbol) → source

    async def load_from_db(self) -> None:
        """Load all multipliers from the database into memory."""
        factory = get_session_factory()
        async with factory() as session:
            # Load base multipliers
            result = await session.execute(select(Follower))
            for follower in result.scalars():
                self._base_multipliers[follower.id] = follower.base_multiplier

            # Load symbol overrides
            result = await session.execute(select(SymbolMultiplier))
            for sm in result.scalars():
                key = (sm.follower_id, sm.symbol)
                self._symbol_overrides[key] = sm.multiplier
                self._symbol_sources[key] = sm.source

        logger.info(
            "Loaded %d base multipliers, %d symbol overrides",
            len(self._base_multipliers),
            len(self._symbol_overrides),
        )

    def get_effective(self, follower_id: str, symbol: str) -> float:
        """Get the effective multiplier for a follower and symbol.

        Resolution: user_override > auto_inferred > base_multiplier > 1.0
        """
        key = (follower_id, symbol)
        if key in self._symbol_overrides:
            return self._symbol_overrides[key]
        return self._base_multipliers.get(follower_id, 1.0)

    def get_source(self, follower_id: str, symbol: str) -> str:
        """Get the source of the effective multiplier."""
        key = (follower_id, symbol)
        if key in self._symbol_sources:
            return self._symbol_sources[key]
        return "base"

    def set_base(self, follower_id: str, multiplier: float) -> None:
        """Update the in-memory base multiplier for a follower."""
        self._base_multipliers[follower_id] = multiplier

    async def set_symbol_override(
        self,
        follower_id: str,
        symbol: str,
        multiplier: float,
        source: str = "user_override",
    ) -> None:
        """Set a per-symbol multiplier override and persist to DB."""
        key = (follower_id, symbol)
        self._symbol_overrides[key] = multiplier
        self._symbol_sources[key] = source

        factory = get_session_factory()
        async with factory() as session:
            # Upsert
            existing = await session.execute(
                select(SymbolMultiplier).where(
                    SymbolMultiplier.follower_id == follower_id,
                    SymbolMultiplier.symbol == symbol,
                )
            )
            sm = existing.scalar_one_or_none()
            if sm:
                sm.multiplier = multiplier
                sm.source = source
            else:
                sm = SymbolMultiplier(
                    follower_id=follower_id,
                    symbol=symbol,
                    multiplier=multiplier,
                    source=source,
                )
                session.add(sm)
            await session.commit()

        logger.info(
            "Set %s multiplier for %s/%s: %.4f",
            source,
            follower_id,
            symbol,
            multiplier,
        )

    async def set_auto_inferred(
        self, follower_id: str, symbol: str, multiplier: float
    ) -> None:
        """Set an auto-inferred multiplier. Does NOT overwrite user overrides."""
        key = (follower_id, symbol)
        current_source = self._symbol_sources.get(key)
        if current_source == "user_override":
            logger.debug(
                "Skipping auto-inferred multiplier for %s/%s: user override exists",
                follower_id,
                symbol,
            )
            return
        await self.set_symbol_override(
            follower_id, symbol, multiplier, source="auto_inferred"
        )

    async def remove_symbol_override(self, follower_id: str, symbol: str) -> None:
        """Remove a per-symbol override, reverting to base multiplier."""
        key = (follower_id, symbol)
        self._symbol_overrides.pop(key, None)
        self._symbol_sources.pop(key, None)

        factory = get_session_factory()
        async with factory() as session:
            existing = await session.execute(
                select(SymbolMultiplier).where(
                    SymbolMultiplier.follower_id == follower_id,
                    SymbolMultiplier.symbol == symbol,
                )
            )
            sm = existing.scalar_one_or_none()
            if sm:
                await session.delete(sm)
                await session.commit()

    def remove_follower(self, follower_id: str) -> None:
        """Clean up all in-memory state for a removed follower."""
        self._base_multipliers.pop(follower_id, None)
        keys_to_remove = [k for k in self._symbol_overrides if k[0] == follower_id]
        for key in keys_to_remove:
            self._symbol_overrides.pop(key, None)
            self._symbol_sources.pop(key, None)

    def get_all_for_follower(self, follower_id: str) -> dict[str, dict[str, Any]]:
        """Get all multiplier info for a follower (base + overrides)."""
        result: dict[str, dict[str, Any]] = {}
        for (fid, sym), mult in self._symbol_overrides.items():
            if fid == follower_id:
                result[sym] = {
                    "multiplier": mult,
                    "source": self._symbol_sources.get((fid, sym), "unknown"),
                }
        return result
