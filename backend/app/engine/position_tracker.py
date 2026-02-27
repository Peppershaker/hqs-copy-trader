"""Position tracker.

Provides position snapshots for the dashboard by reading live data from
master and follower DAS clients.
"""

from __future__ import annotations

import logging
from typing import Any

from das_bridge.domain.positions import Position

from app.engine.multiplier_manager import MultiplierManager
from app.services.das_service import DASService

logger = logging.getLogger(__name__)


class PositionTracker:
    """Reads positions from DAS clients and enriches them with multiplier info."""

    def __init__(
        self,
        das_service: DASService,
        multiplier_mgr: MultiplierManager,
    ) -> None:
        """Initialize the position tracker with its dependencies."""
        self._das = das_service
        self._multiplier_mgr = multiplier_mgr

    @staticmethod
    def _serialize_position(pos: Position) -> dict[str, Any]:
        """Convert a DAS position object to a JSON-serializable dict."""
        unrealized = float(pos.unrealized_pnl)
        realized = float(pos.realized_pnl)
        return {
            "symbol": pos.symbol,
            "side": pos.position_type.name,
            "quantity": pos.quantity,
            "avg_cost": float(pos.avg_cost),
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "total_pnl": realized + unrealized,
            "last_price": float(pos.last_price) if pos.last_price else 0,
        }

    def get_positions_snapshot(self) -> dict[str, Any]:
        """Build a snapshot of all positions for the dashboard."""
        snapshot: dict[str, Any] = {"master": [], "followers": {}}

        master_client = self._das.master_client
        if master_client and master_client.is_running:
            for pos in master_client.positions:
                snapshot["master"].append(self._serialize_position(pos))

        for fid, client in self._das.follower_clients.items():
            if not client.is_running:
                snapshot["followers"][fid] = []
                continue

            positions: list[dict[str, Any]] = []
            for pos in client.positions:
                entry = self._serialize_position(pos)
                entry["effective_multiplier"] = self._multiplier_mgr.get_effective(
                    fid, pos.symbol
                )
                entry["multiplier_source"] = self._multiplier_mgr.get_source(
                    fid, pos.symbol
                )
                positions.append(entry)
            snapshot["followers"][fid] = positions

        return snapshot
