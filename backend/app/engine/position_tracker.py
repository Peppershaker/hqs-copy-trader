"""Position tracker.

Monitors position changes on both master and follower accounts to:
- Detect manual position entries on followers (for multiplier inference)
- Track position state for the dashboard
"""

from __future__ import annotations

import logging
from typing import Any

from app.engine.multiplier_manager import MultiplierManager
from app.services.notification_service import NotificationService
from das_bridge import DASClient

logger = logging.getLogger(__name__)


class PositionTracker:
    """Tracks positions across master and follower accounts.

    Key responsibility: detect when a follower opens a position manually
    (e.g., after accepting locates) and infer the effective multiplier.
    """

    def __init__(
        self,
        multiplier_mgr: MultiplierManager,
        notifier: NotificationService,
    ) -> None:
        self._multiplier_mgr = multiplier_mgr
        self._notifier = notifier

    async def on_follower_position_opened(
        self,
        follower_id: str,
        symbol: str,
        follower_qty: int,
        master_client: DASClient,
    ) -> None:
        """Called when a new position is detected on a follower.

        If the master also has a position in the same symbol,
        infer the effective multiplier.
        """
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

    def get_positions_snapshot(
        self,
        master_client: DASClient | None,
        follower_clients: dict[str, DASClient],
    ) -> dict[str, Any]:
        """Build a snapshot of all positions for the dashboard."""
        snapshot: dict[str, Any] = {"master": [], "followers": {}}

        if master_client and master_client.is_running:
            for pos in master_client.positions:
                unrealized = (
                    float(pos.das_unrealized_pnl) if pos.das_unrealized_pnl else 0.0
                )
                realized = float(pos.realized_pnl)
                snapshot["master"].append(
                    {
                        "symbol": pos.symbol,
                        "side": (
                            str(pos.position_type.name)
                            if hasattr(pos.position_type, "name")
                            else str(pos.position_type)
                        ),
                        "quantity": pos.quantity,
                        "avg_cost": float(pos.avg_cost),
                        "realized_pnl": realized,
                        "unrealized_pnl": unrealized,
                        "total_pnl": realized + unrealized,
                        "last_price": float(pos.last_price) if pos.last_price else 0,
                    }
                )

        for fid, client in follower_clients.items():
            if not client.is_running:
                snapshot["followers"][fid] = []
                continue

            positions: list[dict[str, Any]] = []
            for pos in client.positions:
                unrealized = (
                    float(pos.das_unrealized_pnl) if pos.das_unrealized_pnl else 0.0
                )
                realized = float(pos.realized_pnl)
                positions.append(
                    {
                        "symbol": pos.symbol,
                        "side": (
                            str(pos.position_type.name)
                            if hasattr(pos.position_type, "name")
                            else str(pos.position_type)
                        ),
                        "quantity": pos.quantity,
                        "avg_cost": float(pos.avg_cost),
                        "realized_pnl": realized,
                        "unrealized_pnl": unrealized,
                        "total_pnl": realized + unrealized,
                        "last_price": float(pos.last_price) if pos.last_price else 0,
                        "effective_multiplier": self._multiplier_mgr.get_effective(
                            fid, pos.symbol
                        ),
                        "multiplier_source": self._multiplier_mgr.get_source(
                            fid, pos.symbol
                        ),
                    }
                )
            snapshot["followers"][fid] = positions

        return snapshot
