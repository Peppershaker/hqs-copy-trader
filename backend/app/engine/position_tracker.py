"""Position tracker.

Monitors position changes on both master and follower accounts to:
- Detect manual position entries on followers (for multiplier inference)
- Track position state for the dashboard
"""

from __future__ import annotations

import logging
from typing import Any

from das_bridge.domain.positions import Position

from app.engine.multiplier_manager import MultiplierManager
from app.services.das_service import DASService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class PositionTracker:
    """Tracks positions across master and follower accounts.

    Key responsibility: detect when a follower opens a position manually
    (e.g., after accepting locates) and infer the effective multiplier.
    """

    def __init__(
        self,
        das_service: DASService,
        multiplier_mgr: MultiplierManager,
        notifier: NotificationService,
    ) -> None:
        """Initialize the position tracker with its dependencies."""
        self._das = das_service
        self._multiplier_mgr = multiplier_mgr
        self._notifier = notifier

    async def on_follower_position_opened(
        self,
        follower_id: str,
        symbol: str,
        follower_qty: int,
    ) -> None:
        """Called when a new position is detected on a follower.

        If the master also has a position in the same symbol,
        infer the effective multiplier.
        """
        master_client = self._das.master_client
        if not master_client:
            return
        master_pos = master_client.get_position(symbol)
        if not master_pos or master_pos.quantity == 0:
            return

        inferred = abs(follower_qty) / abs(master_pos.quantity)
        current = self._multiplier_mgr.get_effective(follower_id, symbol)

        # Only update if meaningfully different
        if abs(inferred - current) > 0.01:
            await self._multiplier_mgr.set_auto_inferred(follower_id, symbol, inferred)
            logger.info(
                "Auto-inferred multiplier for %s/%s: %.4f (was %.4f)",
                follower_id,
                symbol,
                inferred,
                current,
            )
            await self._notifier.broadcast(
                "multiplier_inferred",
                {
                    "follower_id": follower_id,
                    "symbol": symbol,
                    "old_multiplier": current,
                    "new_multiplier": round(inferred, 4),
                    "source": "auto_inferred",
                },
            )

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
