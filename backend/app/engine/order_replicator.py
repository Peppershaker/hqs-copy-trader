"""Order replicator.

Handles replicating order actions (submit, cancel, replace) from master to followers.
"""

from __future__ import annotations

import itertools
import logging
from decimal import Decimal
from typing import Any

from das_bridge import DASClient
from das_bridge.domain.orders import (
    BaseOrder,
    LimitOrder,
    MarketOrder,
    StopLimitOrder,
    StopOrder,
    TrailingStopOrder,
)

from app.engine.blacklist_manager import BlacklistManager
from app.engine.multiplier_manager import MultiplierManager
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class OrderReplicator:
    """Submits, cancels, and replaces orders on follower accounts
    based on master order events.
    """

    def __init__(
        self,
        multiplier_mgr: MultiplierManager,
        blacklist_mgr: BlacklistManager,
        audit: AuditService,
        notifier: NotificationService,
    ) -> None:
        self._multiplier_mgr = multiplier_mgr
        self._blacklist_mgr = blacklist_mgr
        self._audit = audit
        self._notifier = notifier

        # master_order_token → {follower_id: follower_order_token}
        self._order_map: dict[int, dict[str, int]] = {}
        # follower_order_token → master_order_token (reverse lookup)
        self._reverse_map: dict[int, int] = {}
        # Token counter for generating unique follower order tokens
        self._token_counter = itertools.count(100_000)

    def _scale_quantity(self, quantity: int, follower_id: str, symbol: str) -> int:
        """Scale a quantity by the effective multiplier, rounded to int."""
        multiplier = self._multiplier_mgr.get_effective(follower_id, symbol)
        scaled = round(quantity * multiplier)
        return max(scaled, 1)  # Never submit 0-share orders

    async def replicate_order(
        self,
        master_order: BaseOrder,
        follower_id: str,
        follower_client: DASClient,
    ) -> int | None:
        """Replicate a master order to a single follower.

        Returns the follower order token on success, None on failure.

        .. todo:: Buying power check before submission.
           If insufficient BP, alert the user instead of submitting.
           Currently not implemented because DAS auto-rejects orders
           that exceed available buying power.
        """
        symbol = master_order.symbol
        scaled_qty = self._scale_quantity(master_order.quantity, follower_id, symbol)

        try:
            result = await self._submit_matching_order(follower_client, master_order, scaled_qty)

            if result and result.token:
                # Track mapping
                master_token = master_order.token
                if master_token not in self._order_map:
                    self._order_map[master_token] = {}
                self._order_map[master_token][follower_id] = result.token
                self._reverse_map[result.token] = master_token

                await self._audit.info(
                    "order",
                    f"Replicated {symbol} order to {follower_id}: "
                    f"qty={scaled_qty} (master={master_order.quantity})",
                    follower_id=follower_id,
                    symbol=symbol,
                    details={
                        "master_token": master_token,
                        "follower_token": result.token,
                        "multiplier": self._multiplier_mgr.get_effective(follower_id, symbol),
                    },
                )
                return result.token

        except Exception as e:
            await self._audit.error(
                "order",
                f"Failed to replicate {symbol} order to {follower_id}: {e}",
                follower_id=follower_id,
                symbol=symbol,
            )
            await self._notifier.broadcast(
                "alert",
                {
                    "level": "error",
                    "message": f"Order replication failed for {symbol} on {follower_id}: {e}",
                },
            )

        return None

    async def _submit_matching_order(
        self,
        client: DASClient,
        master_order: BaseOrder,
        quantity: int,
    ) -> Any:
        """Submit an order on the follower matching the master order type."""
        symbol = master_order.symbol
        side = master_order.side
        token = next(self._token_counter)

        if isinstance(master_order, MarketOrder):
            return await client.place_market_order(
                symbol=symbol,
                quantity=quantity,
                side=side,
                token=token,
            )
        elif isinstance(master_order, LimitOrder):
            return await client.place_limit_order(
                symbol=symbol,
                quantity=quantity,
                side=side,
                price=master_order.price,
                token=token,
            )
        elif isinstance(master_order, StopLimitOrder):
            # StopLimit must be checked before Stop (inheritance)
            order = StopLimitOrder(
                token=token,
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
                token=token,
                symbol=symbol,
                quantity=quantity,
                side=side,
                stop_price=master_order.stop_price,
                time_in_force=master_order.time_in_force,
            )
            return await client.submit_order(order)
        elif isinstance(master_order, TrailingStopOrder):
            order = TrailingStopOrder(
                token=token,
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
        master_order_token: int,
        follower_clients: dict[str, DASClient],
    ) -> dict[str, bool]:
        """Cancel all follower orders that correspond to a master order.

        Returns {follower_id: success_bool}.
        """
        follower_tokens = self._order_map.get(master_order_token, {})
        results: dict[str, bool] = {}

        for follower_id, follower_token in follower_tokens.items():
            client = follower_clients.get(follower_id)
            if not client or not client.is_running:
                results[follower_id] = False
                continue

            try:
                order = client.get_order_by_token(follower_token)
                if order and order.server_order_id:
                    success = await client.cancel_order(order.server_order_id)
                    results[follower_id] = success
                    if success:
                        await self._audit.info(
                            "order",
                            f"Cancelled {order.symbol} order on {follower_id}",
                            follower_id=follower_id,
                            symbol=order.symbol,
                        )
                else:
                    results[follower_id] = False
            except Exception as e:
                results[follower_id] = False
                await self._audit.error(
                    "order",
                    f"Failed to cancel order on {follower_id}: {e}",
                    follower_id=follower_id,
                )

        return results

    async def replace_follower_orders(
        self,
        master_order_token: int,
        new_quantity: int | None,
        new_price: Decimal | None,
        follower_clients: dict[str, DASClient],
    ) -> dict[str, bool]:
        """Replace all follower orders corresponding to a master order.

        Scales quantity but preserves price from master.
        Returns {follower_id: success_bool}.
        """
        follower_tokens = self._order_map.get(master_order_token, {})
        results: dict[str, bool] = {}

        for follower_id, follower_token in follower_tokens.items():
            client = follower_clients.get(follower_id)
            if not client or not client.is_running:
                results[follower_id] = False
                continue

            try:
                order = client.get_order_by_token(follower_token)
                if not order or not order.server_order_id:
                    results[follower_id] = False
                    continue

                # Scale the new quantity
                scaled_qty = order.quantity
                if new_quantity is not None:
                    scaled_qty = self._scale_quantity(new_quantity, follower_id, order.symbol)

                success = await client.replace_order(
                    order.server_order_id,
                    new_quantity=scaled_qty,
                    new_price=new_price,
                )
                results[follower_id] = success

                if success:
                    await self._audit.info(
                        "order",
                        f"Replaced {order.symbol} order on {follower_id}: "
                        f"qty={scaled_qty}, price={new_price}",
                        follower_id=follower_id,
                        symbol=order.symbol,
                    )
            except Exception as e:
                results[follower_id] = False
                await self._audit.error(
                    "order",
                    f"Failed to replace order on {follower_id}: {e}",
                    follower_id=follower_id,
                )

        return results

    def get_follower_tokens(self, master_order_token: int) -> dict[str, int]:
        """Get all follower order tokens for a master order."""
        return dict(self._order_map.get(master_order_token, {}))

    def get_master_token(self, follower_order_token: int) -> int | None:
        """Reverse lookup: follower token → master token."""
        return self._reverse_map.get(follower_order_token)

    def cleanup_order(self, master_order_token: int) -> None:
        """Remove tracking for a completed/cancelled master order."""
        follower_tokens = self._order_map.pop(master_order_token, {})
        for token in follower_tokens.values():
            self._reverse_map.pop(token, None)
