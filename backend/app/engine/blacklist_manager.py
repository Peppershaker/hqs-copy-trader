"""Blacklist manager.

In-memory cache of per-follower, per-symbol blacklist backed by SQLite.
"""

from __future__ import annotations

import logging

from sqlalchemy import delete, select

from app.database import get_session_factory
from app.models.blacklist import BlacklistEntry

logger = logging.getLogger(__name__)


class BlacklistManager:
    """Manages the per-follower, per-symbol blacklist."""

    def __init__(self) -> None:
        # (follower_id, symbol) → reason
        self._blacklist: dict[tuple[str, str], str] = {}

    async def load_from_db(self) -> None:
        """Load all blacklist entries from the database."""
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(select(BlacklistEntry))
            for entry in result.scalars():
                self._blacklist[(entry.follower_id, entry.symbol)] = (
                    entry.reason or "unknown"
                )
        logger.info("Loaded %d blacklist entries", len(self._blacklist))

    def is_blacklisted(self, follower_id: str, symbol: str) -> bool:
        """Check if a symbol is blacklisted for a specific follower."""
        return (follower_id, symbol.upper()) in self._blacklist

    def get_blacklisted_symbols(self, follower_id: str) -> list[str]:
        """Get all blacklisted symbols for a specific follower."""
        return [sym for (fid, sym) in self._blacklist if fid == follower_id]

    def get_all(self) -> dict[tuple[str, str], str]:
        """Return all blacklist entries."""
        return dict(self._blacklist)

    async def add(self, follower_id: str, symbol: str, reason: str = "manual") -> bool:
        """Add a symbol to the blacklist for a follower.

        Returns True if added, False if already blacklisted.
        """
        symbol = symbol.upper()
        key = (follower_id, symbol)
        if key in self._blacklist:
            return False

        self._blacklist[key] = reason

        factory = get_session_factory()
        async with factory() as session:
            entry = BlacklistEntry(
                follower_id=follower_id,
                symbol=symbol,
                reason=reason,
            )
            session.add(entry)
            await session.commit()

        logger.info(
            "Blacklisted %s on follower %s (reason: %s)", symbol, follower_id, reason
        )
        return True

    async def remove(self, follower_id: str, symbol: str) -> bool:
        """Remove a symbol from the blacklist.

        Returns True if removed, False if not found.
        """
        symbol = symbol.upper()
        key = (follower_id, symbol)
        if key not in self._blacklist:
            return False

        del self._blacklist[key]

        factory = get_session_factory()
        async with factory() as session:
            await session.execute(
                delete(BlacklistEntry).where(
                    BlacklistEntry.follower_id == follower_id,
                    BlacklistEntry.symbol == symbol,
                )
            )
            await session.commit()

        logger.info("Un-blacklisted %s on follower %s", symbol, follower_id)
        return True

    async def remove_by_id(self, entry_id: int) -> bool:
        """Remove a blacklist entry by its database ID."""
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(BlacklistEntry).where(BlacklistEntry.id == entry_id)
            )
            entry = result.scalar_one_or_none()
            if not entry:
                return False

            key = (entry.follower_id, entry.symbol)
            self._blacklist.pop(key, None)
            await session.delete(entry)
            await session.commit()
            return True

    def remove_follower(self, follower_id: str) -> None:
        """Remove all in-memory blacklist entries for a follower."""
        keys_to_remove = [k for k in self._blacklist if k[0] == follower_id]
        for key in keys_to_remove:
            del self._blacklist[key]
