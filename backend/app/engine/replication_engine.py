"""Replication engine — the main orchestrator.

Subscribes to master DASClient events and coordinates replication
to all follower accounts through the specialized sub-engines.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from das_bridge import DASClient
from das_bridge.domain.events.order_events import (
    OrderAcceptedEvent,
    OrderCancelledEvent,
    OrderReplacedEvent,
)
from das_bridge.domain.events.position_events import (
    PositionOpenedEvent,
)
from das_bridge.domain.events.short_locate_events import (
    LocateOrderUpdatedEvent,
)

from app.engine.action_queue import ActionQueue, QueuedActionType
from app.engine.blacklist_manager import BlacklistManager
from app.engine.locate_replicator import LocateReplicator
from app.engine.multiplier_manager import MultiplierManager
from app.engine.order_replicator import OrderReplicator
from app.engine.position_tracker import PositionTracker
from app.services.audit_service import AuditService
from app.services.das_service import DASService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

_E = TypeVar("_E")


def _fire(coro_fn: Callable[[_E], Coroutine[Any, Any, None]]) -> Callable[[_E], None]:
    """Wrap an async handler so it can be passed to ``DASClient.on()``."""

    def wrapper(event: _E) -> None:
        asyncio.ensure_future(coro_fn(event))

    return wrapper


class ReplicationEngine:
    """Main orchestrator for the copy trading system.

    Subscribes to events on the master DASClient and replicates actions
    to all enabled follower accounts.
    """

    def __init__(
        self,
        das_service: DASService,
        notifier: NotificationService,
        audit: AuditService,
    ) -> None:
        self._das = das_service
        self._notifier = notifier
        self._audit = audit

        # Sub-engines
        self._multiplier_mgr = MultiplierManager()
        self._blacklist_mgr = BlacklistManager()
        self._order_replicator = OrderReplicator(
            self._multiplier_mgr,
            self._blacklist_mgr,
            audit,
            notifier,
        )
        self._locate_replicator = LocateReplicator(
            self._multiplier_mgr,
            self._blacklist_mgr,
            audit,
            notifier,
        )
        self._position_tracker = PositionTracker(
            self._multiplier_mgr,
            notifier,
        )

        # Disconnected-follower action queue
        self._action_queue = ActionQueue()

        # Event unsubscribe callbacks
        self._unsubscribers: list[Any] = []
        self._running = False

        # Follower configs cache (loaded from DB)
        self._follower_configs: dict[str, dict[str, Any]] = {}

        # State push task
        self._state_push_task: asyncio.Task[None] | None = None

        # Reconnect detection: track previous ``is_running`` per follower
        self._prev_follower_connected: dict[str, bool] = {}

    @property
    def action_queue(self) -> ActionQueue:
        return self._action_queue

    @property
    def multiplier_manager(self) -> MultiplierManager:
        return self._multiplier_mgr

    @property
    def blacklist_manager(self) -> BlacklistManager:
        return self._blacklist_mgr

    @property
    def order_replicator(self) -> OrderReplicator:
        return self._order_replicator

    @property
    def locate_replicator(self) -> LocateReplicator:
        return self._locate_replicator

    @property
    def position_tracker(self) -> PositionTracker:
        return self._position_tracker

    async def start(self, follower_configs: dict[str, dict[str, Any]] | None = None) -> None:
        """Initialize state and subscribe to master events."""
        if self._running:
            return

        # Load persistent state
        await self._multiplier_mgr.load_from_db()
        await self._blacklist_mgr.load_from_db()

        if follower_configs:
            self._follower_configs = follower_configs

        # Subscribe to master events
        master = self._das.master_client
        if master:
            self._subscribe_to_master(master)
            self._subscribe_to_followers()

        # Start periodic state push to UI
        self._state_push_task = asyncio.create_task(self._state_push_loop())

        self._running = True
        await self._audit.info("system", "Replication engine started")
        logger.info("Replication engine started")

    async def stop(self) -> None:
        """Unsubscribe from events and clean up."""
        if not self._running:
            return

        # Cancel state push
        if self._state_push_task:
            self._state_push_task.cancel()
            try:
                await self._state_push_task
            except asyncio.CancelledError:
                pass

        # Cancel locate retries
        await self._locate_replicator.cancel_all_retries()

        # Unsubscribe from events
        for unsub in self._unsubscribers:
            if callable(unsub):
                unsub()
        self._unsubscribers.clear()

        self._running = False
        await self._audit.info("system", "Replication engine stopped")
        logger.info("Replication engine stopped")

    def _subscribe_to_master(self, master: DASClient) -> None:
        """Subscribe to master order/locate events."""

        # Order accepted → replicate to followers
        unsub = master.on(OrderAcceptedEvent, _fire(self._on_master_order_accepted))
        self._unsubscribers.append(unsub)

        # Order cancelled → cancel follower orders
        unsub = master.on(OrderCancelledEvent, _fire(self._on_master_order_cancelled))
        self._unsubscribers.append(unsub)

        # Order replaced → replace follower orders
        unsub = master.on(OrderReplacedEvent, _fire(self._on_master_order_replaced))
        self._unsubscribers.append(unsub)

        # Locate filled → replicate to followers
        unsub = master.on(LocateOrderUpdatedEvent, _fire(self._on_master_locate_updated))
        self._unsubscribers.append(unsub)

        logger.info("Subscribed to master events")

    def _subscribe_to_followers(self) -> None:
        """Subscribe to position events on all follower clients."""
        for fid, client in self._das.follower_clients.items():

            def _make_handler(
                _fid: str,
            ) -> Callable[[PositionOpenedEvent], None]:
                def handler(event: PositionOpenedEvent) -> None:
                    asyncio.ensure_future(self._on_follower_position_opened(event, _fid))

                return handler

            unsub = client.on(PositionOpenedEvent, _make_handler(fid))
            self._unsubscribers.append(unsub)

    # --- Master event handlers ---

    async def _on_master_order_accepted(self, event: OrderAcceptedEvent) -> None:
        """Master order accepted → replicate to all enabled followers."""
        master = self._das.master_client
        if not master:
            return

        order = master.get_order(event.order_id)
        if not order:
            logger.warning("Master order %s not found for replication", event.order_id)
            return

        # Skip DAS Bridge server-status probe orders (SPY via TESTROUTE)
        if order.symbol == "SPY" and order.route == "TESTROUTE":
            logger.debug("Ignoring probe order %s (SPY/TESTROUTE)", event.order_id)
            return

        followers = self._das.follower_clients
        results: dict[str, int | None] = {}

        for fid, client in followers.items():
            # Skip blacklisted
            if self._blacklist_mgr.is_blacklisted(fid, order.symbol):
                continue
            # If disconnected → queue the action for later replay
            if not client.is_running:
                self._action_queue.enqueue(
                    follower_id=fid,
                    action_type=QueuedActionType.ORDER_SUBMIT,
                    symbol=order.symbol,
                    payload={
                        "order_snapshot": {
                            "type": type(order).__name__,
                            "symbol": order.symbol,
                            "side": str(order.side),
                            "quantity": order.quantity,
                            "token": order.token,
                            "price": str(getattr(order, "price", "")),
                            "stop_price": str(getattr(order, "stop_price", "")),
                            "limit_price": str(getattr(order, "limit_price", "")),
                        },
                    },
                )
                await self._audit.warn(
                    "order",
                    f"Follower {fid} offline — queued replication of {order.symbol}",
                    follower_id=fid,
                    symbol=order.symbol,
                )
                await self._notifier.broadcast(
                    "action_queued",
                    {
                        "follower_id": fid,
                        "action_type": "order_submit",
                        "symbol": order.symbol,
                        "message": f"Follower {fid} offline — order for {order.symbol} queued",
                    },
                )
                results[fid] = None
                continue

            token = await self._order_replicator.replicate_order(order, fid, client)
            results[fid] = token

        # Notify UI
        await self._notifier.broadcast(
            "order_replicated",
            {
                "symbol": order.symbol,
                "master_order_id": event.order_id,
                "master_token": order.token,
                "side": str(order.side),
                "quantity": order.quantity,
                "type": type(order).__name__,
                "follower_results": {
                    fid: {"token": t, "success": t is not None} for fid, t in results.items()
                },
            },
        )

    async def _on_master_order_cancelled(self, event: OrderCancelledEvent) -> None:
        """Master order cancelled → cancel corresponding follower orders."""
        master = self._das.master_client
        if not master:
            return

        order = master.get_order(event.order_id)
        token = order.token if order else None
        if not token:
            return

        # Skip DAS Bridge server-status probe orders (SPY via TESTROUTE)
        if order and order.symbol == "SPY" and order.route == "TESTROUTE":
            logger.debug("Ignoring probe cancel %s (SPY/TESTROUTE)", event.order_id)
            return

        # Queue cancels for disconnected followers
        for fid, client in self._das.follower_clients.items():
            if not client.is_running:
                symbol = order.symbol if order else "UNKNOWN"
                self._action_queue.enqueue(
                    follower_id=fid,
                    action_type=QueuedActionType.ORDER_CANCEL,
                    symbol=symbol,
                    payload={"master_order_token": token},
                )
                await self._notifier.broadcast(
                    "action_queued",
                    {
                        "follower_id": fid,
                        "action_type": "order_cancel",
                        "symbol": symbol,
                        "message": f"Follower {fid} offline — cancel for {symbol} queued",
                    },
                )

        results = await self._order_replicator.cancel_follower_orders(
            token, self._das.follower_clients
        )

        await self._notifier.broadcast(
            "order_cancelled",
            {
                "master_order_id": event.order_id,
                "master_token": token,
                "follower_results": results,
            },
        )

    async def _on_master_order_replaced(self, event: OrderReplacedEvent) -> None:
        """Master order replaced → replace corresponding follower orders."""
        master = self._das.master_client
        if not master:
            return

        order = master.get_order(event.order_id)
        if not order:
            return

        # Queue replaces for disconnected followers
        for fid, client in self._das.follower_clients.items():
            if not client.is_running:
                self._action_queue.enqueue(
                    follower_id=fid,
                    action_type=QueuedActionType.ORDER_REPLACE,
                    symbol=order.symbol,
                    payload={
                        "master_order_token": order.token,
                        "new_quantity": order.quantity,
                        "new_price": str(getattr(order, "price", "")),
                    },
                )
                await self._notifier.broadcast(
                    "action_queued",
                    {
                        "follower_id": fid,
                        "action_type": "order_replace",
                        "symbol": order.symbol,
                        "message": f"Follower {fid} offline — replace for {order.symbol} queued",
                    },
                )

        results = await self._order_replicator.replace_follower_orders(
            order.token,
            new_quantity=order.quantity,
            new_price=getattr(order, "price", None),
            follower_clients=self._das.follower_clients,
        )

        await self._notifier.broadcast(
            "order_replaced",
            {
                "master_order_id": event.order_id,
                "master_token": order.token,
                "follower_results": results,
            },
        )

    async def _on_master_locate_updated(self, event: LocateOrderUpdatedEvent) -> None:
        """Master locate order updated — if filled, replicate to followers."""
        master = self._das.master_client
        if not master:
            return

        # Only process filled locates
        # Check the event for a 'filled' or 'executed' status
        if not hasattr(event, "status") or event.status not in (
            "FILLED",
            "EXECUTED",
            "filled",
            "executed",
        ):
            return

        symbol = event.symbol
        qty = event.executed_shares if hasattr(event, "executed_shares") else 0
        price = event.execution_price if hasattr(event, "execution_price") else 0

        if qty <= 0:
            return

        for fid, client in self._das.follower_clients.items():
            if not client.is_running:
                config = self._follower_configs.get(fid, {})
                self._action_queue.enqueue(
                    follower_id=fid,
                    action_type=QueuedActionType.LOCATE,
                    symbol=symbol,
                    payload={
                        "master_qty": qty,
                        "master_price": float(price),
                        "follower_config": config,
                    },
                )
                await self._notifier.broadcast(
                    "action_queued",
                    {
                        "follower_id": fid,
                        "action_type": "locate",
                        "symbol": symbol,
                        "message": f"Follower {fid} offline — locate for {symbol} queued",
                    },
                )
                continue

            config = self._follower_configs.get(fid, {})
            await self._locate_replicator.replicate_locate(
                symbol=symbol,
                master_qty=qty,
                master_price=float(price),
                follower_id=fid,
                follower_client=client,
                follower_config=config,
            )

    # --- Follower event handlers ---

    async def _on_follower_position_opened(
        self, event: PositionOpenedEvent, follower_id: str
    ) -> None:
        """Follower opened a new position — infer multiplier if applicable."""
        master = self._das.master_client
        if not master:
            return

        await self._position_tracker.on_follower_position_opened(
            follower_id=follower_id,
            symbol=event.symbol,
            follower_qty=event.initial_quantity,
            master_client=master,
        )

    # --- State push loop ---

    async def _state_push_loop(self) -> None:
        """Periodically push full state to all connected WebSocket clients.

        Also detects follower reconnections and notifies the UI about
        queued actions that are ready for replay.
        """
        while True:
            try:
                await asyncio.sleep(1.0)  # 1Hz update rate

                # --- Reconnect detection ---
                await self._check_reconnections()

                if self._notifier.client_count == 0:
                    continue

                state = self._build_full_state()
                await self._notifier.broadcast("state_update", state)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("State push error: %s", e)
                await asyncio.sleep(5.0)

    async def _check_reconnections(self) -> None:
        """Detect followers that transitioned from disconnected → connected.

        When a follower reconnects and has queued actions, notify the UI so
        the user can choose which actions to replay.
        """
        for fid, client in self._das.follower_clients.items():
            now_connected = client.is_running
            was_connected = self._prev_follower_connected.get(fid, False)
            self._prev_follower_connected[fid] = now_connected

            if now_connected and not was_connected and self._action_queue.has_pending(fid):
                pending = self._action_queue.pending_summary(fid)
                logger.info(
                    "Follower %s reconnected with %d queued actions",
                    fid,
                    len(pending),
                )
                await self._audit.info(
                    "system",
                    f"Follower {fid} reconnected — "
                    f"{len(pending)} queued action(s) ready for replay",
                    follower_id=fid,
                )
                await self._notifier.broadcast(
                    "queued_actions_available",
                    {
                        "follower_id": fid,
                        "actions": pending,
                    },
                )

    def _build_full_state(self) -> dict[str, Any]:
        """Build the full system state for the UI."""
        master = self._das.master_client
        followers = self._das.follower_clients

        # Positions
        positions = self._position_tracker.get_positions_snapshot(master, followers)

        # Connection status
        status = self._das.get_status()

        # Orders
        master_orders: list[dict[str, Any]] = []
        if master and master.is_running:
            for os in master.active_orders:
                master_orders.append(
                    {
                        "order_id": os.order_id,
                        "token": os.token,
                        "symbol": os.symbol,
                        "side": str(os.order.side),
                        "quantity": os.order.quantity,
                        "status": str(os.status),
                    }
                )

        return {
            "status": status,
            "positions": positions,
            "master_orders": master_orders,
        }

    # --- Queued-action replay ---

    async def replay_queued_actions(
        self, follower_id: str, action_ids: list[str]
    ) -> dict[str, Any]:
        """Replay user-selected queued actions on a reconnected follower.

        Returns a summary of results per action id.
        """
        client = self._das.follower_clients.get(follower_id)
        if not client or not client.is_running:
            return {"error": f"Follower {follower_id} is not connected"}

        removed = self._action_queue.remove(follower_id, set(action_ids))
        master = self._das.master_client
        results: dict[str, dict[str, Any]] = {}

        for action in removed:
            try:
                result = await self._replay_single(action, client, master)
                results[action.id] = {"success": True, **result}
                await self._audit.info(
                    "replay",
                    f"Replayed {action.action_type.value} for {action.symbol} on {follower_id}",
                    follower_id=follower_id,
                    symbol=action.symbol,
                )
            except Exception as e:
                results[action.id] = {"success": False, "error": str(e)}
                await self._audit.error(
                    "replay",
                    f"Failed to replay {action.action_type.value} "
                    f"for {action.symbol} on {follower_id}: {e}",
                    follower_id=follower_id,
                    symbol=action.symbol,
                )

        await self._notifier.broadcast(
            "actions_replayed",
            {
                "follower_id": follower_id,
                "results": results,
            },
        )
        return {"replayed": len(removed), "results": results}

    async def discard_queued_actions(self, follower_id: str, action_ids: list[str]) -> int:
        """Discard (remove without replaying) selected queued actions."""
        removed = self._action_queue.remove(follower_id, set(action_ids))
        return len(removed)

    async def _replay_single(
        self,
        action: Any,
        follower_client: DASClient,
        master: DASClient | None,
    ) -> dict[str, Any]:
        """Execute a single queued action. Returns a result dict."""
        from app.engine.action_queue import QueuedActionType

        if action.action_type == QueuedActionType.ORDER_SUBMIT:
            snap = action.payload.get("order_snapshot", {})
            # We need the master order object; try to fetch it by token
            master_token = snap.get("token")
            master_order = (
                master.get_order_by_token(master_token) if master and master_token else None
            )
            if master_order:
                token = await self._order_replicator.replicate_order(
                    master_order, action.follower_id, follower_client
                )
                return {"follower_token": token}
            else:
                return {"skipped": True, "reason": "Master order no longer exists"}

        elif action.action_type == QueuedActionType.ORDER_CANCEL:
            master_token = action.payload.get("master_order_token")
            if master_token:
                res = await self._order_replicator.cancel_follower_orders(
                    master_token, {action.follower_id: follower_client}
                )
                return {"cancel_result": res.get(action.follower_id, False)}
            return {"skipped": True, "reason": "No master token"}

        elif action.action_type == QueuedActionType.ORDER_REPLACE:
            master_token = action.payload.get("master_order_token")
            new_qty = action.payload.get("new_quantity")
            new_price_str = action.payload.get("new_price", "")
            from decimal import Decimal

            new_price = Decimal(new_price_str) if new_price_str else None
            if master_token:
                res = await self._order_replicator.replace_follower_orders(
                    master_token,
                    new_quantity=new_qty,
                    new_price=new_price,
                    follower_clients={action.follower_id: follower_client},
                )
                return {"replace_result": res.get(action.follower_id, False)}
            return {"skipped": True, "reason": "No master token"}

        elif action.action_type == QueuedActionType.LOCATE:
            payload = action.payload
            config = payload.get("follower_config", {})
            await self._locate_replicator.replicate_locate(
                symbol=action.symbol,
                master_qty=payload["master_qty"],
                master_price=payload["master_price"],
                follower_id=action.follower_id,
                follower_client=follower_client,
                follower_config=config,
            )
            return {"locate_started": True}

        return {"skipped": True, "reason": f"Unknown action type: {action.action_type}"}
