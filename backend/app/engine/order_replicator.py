"""Order replicator.

Handles replicating order actions (submit, cancel, replace) from master to followers.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from das_bridge import DASClient
from das_bridge.domain.orders import (
    BaseOrder,
    LimitOrder,
    MarketOrder,
    OrderResult,
    StopLimitOrder,
    StopOrder,
    TrailingStopOrder,
)

from app.engine.blacklist_manager import BlacklistManager
from app.engine.multiplier_manager import MultiplierManager
from app.services.das_service import DASService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class OrderReplicator:
    """Submits, cancels, and replaces orders on follower accounts.

    Based on master order events.
    """

    def __init__(
        self,
        das_service: DASService,
        multiplier_mgr: MultiplierManager,
        blacklist_mgr: BlacklistManager,
        notifier: NotificationService,
    ) -> None:
        """Initialize the order replicator with its dependencies."""
        self._das = das_service
        self._multiplier_mgr = multiplier_mgr
        self._blacklist_mgr = blacklist_mgr
        self._notifier = notifier

        # master_order_id → {follower_id: follower_order_id}
        self._order_map: dict[int, dict[str, int]] = {}
        # follower_order_id → master_order_id (reverse lookup)
        self._reverse_map: dict[int, int] = {}

    def _scale_quantity(self, quantity: int, follower_id: str, symbol: str) -> int:
        """Scale a quantity by the effective multiplier, rounded to int."""
        multiplier = self._multiplier_mgr.get_effective(follower_id, symbol)
        source = self._multiplier_mgr.get_source(follower_id, symbol)
        scaled = round(quantity * multiplier)
        result = max(scaled, 0)  # Non-negative, 0 means skip
        logger.debug(
            "Scale qty: follower=%s symbol=%s master_qty=%d "
            "multiplier=%.4f source=%s -> %d",
            follower_id,
            symbol,
            quantity,
            multiplier,
            source,
            result,
        )
        return result

    def _get_follower(self, follower_id: str) -> DASClient | None:
        """Get a connected follower client, or None."""
        return self._das.get_connected_follower(follower_id)

    async def replicate_order(
        self,
        master_order: BaseOrder,
        follower_id: str,
        master_order_id: int,
    ) -> int | None:
        """Replicate a master order to a single follower.

        Returns the follower order_id on success, None on failure.

        .. todo:: Buying power check before submission.
           If insufficient BP, alert the user instead of submitting.
           Currently not implemented because DAS auto-rejects orders
           that exceed available buying power.
        """
        client = self._get_follower(follower_id)
        if not client:
            return None

        symbol = master_order.symbol
        scaled_qty = self._scale_quantity(master_order.quantity, follower_id, symbol)

        if scaled_qty == 0:
            logger.info(
                "Skipping %s replication to %s: scaled quantity is 0",
                symbol,
                follower_id,
            )
            return None

        logger.debug(
            "Submitting %s to %s: symbol=%s side=%s qty=%d",
            type(master_order).__name__,
            follower_id,
            symbol,
            master_order.side,
            scaled_qty,
        )

        try:
            result = await self._submit_matching_order(client, master_order, scaled_qty)

            if result and result.is_rejected:
                logger.error(
                    "Order rejected for %s on %s: %s",
                    symbol,
                    follower_id,
                    result.message,
                )
                await self._notifier.broadcast(
                    "alert",
                    {
                        "level": "error",
                        "message": (
                            f"Order rejected for {symbol}"
                            f" on {follower_id}:"
                            f" {result.message}"
                        ),
                    },
                )
                return None

            if result and result.is_success and result.order_id is not None:
                follower_order_id = result.order_id
                # Track mapping
                if master_order_id not in self._order_map:
                    self._order_map[master_order_id] = {}
                self._order_map[master_order_id][follower_id] = follower_order_id
                self._reverse_map[follower_order_id] = master_order_id

                logger.info(
                    "Replicated %s order to %s: qty=%d (master=%d) "
                    "master_oid=%s follower_oid=%s multiplier=%.4f",
                    symbol,
                    follower_id,
                    scaled_qty,
                    master_order.quantity,
                    master_order_id,
                    follower_order_id,
                    self._multiplier_mgr.get_effective(follower_id, symbol),
                )
                return follower_order_id

            # Unexpected status — not rejected, not successful
            logger.warning(
                "Unexpected order result for %s on %s: status=%s "
                "order_id=%s message=%s",
                symbol,
                follower_id,
                result.status if result else "no_result",
                result.order_id if result else None,
                result.message if result else None,
            )
            await self._notifier.broadcast(
                "alert",
                {
                    "level": "warn",
                    "message": (
                        f"Unexpected order status for {symbol}"
                        f" on {follower_id}:"
                        f" {result.status if result else 'no result'}"
                    ),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to replicate %s order to %s: %s",
                symbol,
                follower_id,
                e,
            )
            await self._notifier.broadcast(
                "alert",
                {
                    "level": "error",
                    "message": (
                        f"Order replication failed for "
                        f"{symbol} on {follower_id}: {e}"
                    ),
                },
            )

        return None

    async def _submit_matching_order(
        self,
        client: DASClient,
        master_order: BaseOrder,
        quantity: int,
    ) -> OrderResult:
        """Submit an order on the follower matching the master order type.

        Token generation is handled by das-bridge's OrderManager.
        """
        symbol = master_order.symbol
        side = master_order.side

        if isinstance(master_order, MarketOrder):
            return await client.place_market_order(
                symbol=symbol,
                quantity=quantity,
                side=side,
            )
        elif isinstance(master_order, LimitOrder):
            return await client.place_limit_order(
                symbol=symbol,
                quantity=quantity,
                side=side,
                price=master_order.price,
            )
        elif isinstance(master_order, StopLimitOrder):
            # StopLimit must be checked before Stop (inheritance)
            order = StopLimitOrder(
                symbol=symbol,
                quantity=quantity,
                side=side,
                stop_price=master_order.stop_price,
                limit_price=master_order.limit_price,
                time_in_force=master_order.time_in_force,
            )
            return await client.submit_order(order)
        elif isinstance(master_order, StopOrder):
            order = StopOrder(
                symbol=symbol,
                quantity=quantity,
                side=side,
                stop_price=master_order.stop_price,
                time_in_force=master_order.time_in_force,
            )
            return await client.submit_order(order)
        elif isinstance(master_order, TrailingStopOrder):
            order = TrailingStopOrder(
                symbol=symbol,
                quantity=quantity,
                side=side,
                trail_amount=master_order.trail_amount,
                time_in_force=master_order.time_in_force,
            )
            return await client.submit_order(order)
        else:
            # For any other order type, try generic submission
            logger.warning(
                "Unknown order type %s, attempting generic submit",
                type(master_order).__name__,
            )
            return await client.submit_order(master_order)

    async def cancel_follower_orders(
        self,
        master_order_id: int,
    ) -> dict[str, bool]:
        """Cancel all follower orders that correspond to a master order.

        Returns {follower_id: success_bool}.
        """
        follower_ids = self._order_map.get(master_order_id, {})
        results: dict[str, bool] = {}

        for follower_id, follower_order_id in follower_ids.items():
            client = self._get_follower(follower_id)
            if not client:
                results[follower_id] = False
                continue

            try:
                success = await client.cancel_order(follower_order_id)
                results[follower_id] = success
                order = client.get_order(follower_order_id)
                symbol = order.symbol if order else "UNKNOWN"
                if success:
                    logger.info(
                        "Cancelled %s order on %s (follower_oid=%s)",
                        symbol,
                        follower_id,
                        follower_order_id,
                    )
                else:
                    logger.warning(
                        "Cancel failed for %s order on %s (follower_oid=%s)",
                        symbol,
                        follower_id,
                        follower_order_id,
                    )
                    await self._notifier.broadcast(
                        "alert",
                        {
                            "level": "warn",
                            "message": (
                                f"Cancel failed for {symbol}"
                                f" on {follower_id}"
                            ),
                        },
                    )
            except Exception as e:
                results[follower_id] = False
                logger.error(
                    "Failed to cancel order on %s: %s",
                    follower_id,
                    e,
                )

        return results

    async def replace_follower_orders(
        self,
        master_order_id: int,
        new_quantity: int | None,
        new_price: Decimal | None,
    ) -> dict[str, bool]:
        """Replace all follower orders corresponding to a master order.

        Scales quantity but preserves price from master.
        Returns {follower_id: success_bool}.
        """
        follower_ids = self._order_map.get(master_order_id, {})
        results: dict[str, bool] = {}

        for follower_id, follower_order_id in follower_ids.items():
            client = self._get_follower(follower_id)
            if not client:
                results[follower_id] = False
                continue

            try:
                order = client.get_order(follower_order_id)
                if not order:
                    results[follower_id] = False
                    continue

                # Scale the new quantity
                scaled_qty = order.quantity
                if new_quantity is not None:
                    scaled_qty = self._scale_quantity(
                        new_quantity, follower_id, order.symbol
                    )

                success = await client.replace_order(
                    follower_order_id,
                    new_quantity=scaled_qty,
                    new_price=new_price,
                )
                results[follower_id] = success

                if success:
                    logger.info(
                        "Replaced %s order on %s: qty=%d price=%s",
                        order.symbol,
                        follower_id,
                        scaled_qty,
                        new_price,
                    )
                else:
                    logger.warning(
                        "Replace failed for %s order on %s "
                        "(follower_oid=%s qty=%d price=%s)",
                        order.symbol,
                        follower_id,
                        follower_order_id,
                        scaled_qty,
                        new_price,
                    )
                    await self._notifier.broadcast(
                        "alert",
                        {
                            "level": "warn",
                            "message": (
                                f"Replace failed for {order.symbol}"
                                f" on {follower_id}"
                            ),
                        },
                    )
            except Exception as e:
                results[follower_id] = False
                logger.error(
                    "Failed to replace order on %s: %s",
                    follower_id,
                    e,
                )

        return results

    def get_follower_order_ids(self, master_order_id: int) -> dict[str, int]:
        """Get all follower order IDs for a master order."""
        return dict(self._order_map.get(master_order_id, {}))

    def get_master_order_id(self, follower_order_id: int) -> int | None:
        """Reverse lookup: follower order_id → master order_id."""
        return self._reverse_map.get(follower_order_id)

    def cleanup_order(self, master_order_id: int) -> None:
        """Remove tracking for a completed/cancelled master order."""
        follower_ids = self._order_map.pop(master_order_id, {})
        for oid in follower_ids.values():
            self._reverse_map.pop(oid, None)
