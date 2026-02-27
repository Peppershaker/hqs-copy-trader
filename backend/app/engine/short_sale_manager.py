"""Short sale manager.

Handles the on-demand locate-then-short workflow. When the master places
a short sale order, the manager checks the follower's current selling
capacity via ``get_max_sell()``.  If the follower lacks capacity, we
auto-locate exactly the deficit via ``smart_locate()`` before placing the
order.

Concurrency controls:
  - Per-(follower, symbol) ``asyncio.Lock`` prevents double-locating when
    multiple shorts on the same symbol arrive in quick succession.
  - A global ``asyncio.Semaphore`` caps the number of concurrent
    ``smart_locate()`` calls to respect DAS API limits.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from das_bridge.domain.orders import BaseOrder

from app.engine.blacklist_manager import BlacklistManager
from app.engine.multiplier_manager import MultiplierManager
from app.services.notification_service import NotificationService

if TYPE_CHECKING:
    from app.engine.order_replicator import OrderReplicator
    from app.services.das_service import DASService

logger = logging.getLogger(__name__)

# Default maximum concurrent smart_locate calls across all followers.
_DEFAULT_MAX_CONCURRENT_LOCATES = 3


@dataclass
class ShortSaleTask:
    """Tracks a single locate-then-short workflow for one follower."""

    id: str
    follower_id: str
    symbol: str
    master_order_id: int
    required_qty: int
    status: str = "pending"
    locate_deficit: int = 0
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    follower_order_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dictionary for serialisation."""
        d = asdict(self)
        return d


class ShortSaleManager:
    """Manages on-demand locate + short-order placement for followers."""

    def __init__(
        self,
        das_service: DASService,
        multiplier_mgr: MultiplierManager,
        blacklist_mgr: BlacklistManager,
        order_replicator: OrderReplicator,
        notifier: NotificationService,
        *,
        max_concurrent_locates: int = _DEFAULT_MAX_CONCURRENT_LOCATES,
    ) -> None:
        """Initialize the short sale manager with its dependencies."""
        self._das = das_service
        self._multiplier_mgr = multiplier_mgr
        self._blacklist_mgr = blacklist_mgr
        self._order_replicator = order_replicator
        self._notifier = notifier

        # Task tracking
        self._tasks: dict[str, ShortSaleTask] = {}
        self._task_futures: dict[str, asyncio.Task[None]] = {}
        self._counter = 0

        # Concurrency control
        self._global_semaphore = asyncio.Semaphore(max_concurrent_locates)
        self._symbol_locks: dict[tuple[str, str], asyncio.Lock] = {}

        # Master orders cancelled while a locate was in-flight
        self._cancelled_master_orders: set[int] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def handle_short_sale(
        self,
        master_order: BaseOrder,
        follower_id: str,
        master_order_id: int,
        follower_config: dict[str, Any],
    ) -> str:
        """Entry point called by ReplicationEngine for short sale orders.

        Creates a task and starts execution in the background.
        Returns the task ID.
        """
        symbol = master_order.symbol
        multiplier = self._multiplier_mgr.get_effective(follower_id, symbol)
        required_qty = max(round(master_order.quantity * multiplier), 1)

        task = ShortSaleTask(
            id=self._next_id(),
            follower_id=follower_id,
            symbol=symbol,
            master_order_id=master_order_id,
            required_qty=required_qty,
        )
        self._tasks[task.id] = task

        await self._broadcast_task(task)

        future = asyncio.create_task(
            self._execute_task(task, master_order, follower_config),
            name=f"short-sale-{task.id}",
        )
        future.add_done_callback(self._task_done_callback)
        self._task_futures[task.id] = future

        logger.info(
            "Short sale task %s created: follower=%s symbol=%s qty=%d",
            task.id,
            follower_id,
            symbol,
            required_qty,
        )
        return task.id

    async def on_master_order_cancelled(self, master_order_id: int) -> None:
        """Called when the master cancels an order.

        If any in-flight short-sale tasks reference this order,
        cancel them so we don't locate/place an unwanted order.
        """
        self._cancelled_master_orders.add(master_order_id)

        for task_id, task in list(self._tasks.items()):
            if task.master_order_id == master_order_id and task.status in (
                "pending",
                "checking",
                "locating",
            ):
                logger.info(
                    "Cancelling short sale task %s — master order %s cancelled",
                    task_id,
                    master_order_id,
                )
                await self.cancel_task(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a short-sale task by ID (user or system initiated)."""
        future = self._task_futures.get(task_id)
        if future and not future.done():
            future.cancel()
            return True

        task = self._tasks.get(task_id)
        if task and task.status in ("pending", "checking", "locating"):
            task.status = "cancelled"
            await self._broadcast_task(task)
            return True

        return False

    def get_active_tasks(self) -> list[dict[str, Any]]:
        """Return all non-terminal tasks for the UI."""
        return [
            t.to_dict()
            for t in self._tasks.values()
            if t.status not in ("completed", "failed", "cancelled")
        ]

    def get_all_tasks(self) -> list[dict[str, Any]]:
        """Return all tasks (including terminal) for debugging/API."""
        return [t.to_dict() for t in self._tasks.values()]

    async def cancel_all(self) -> None:
        """Cancel every in-flight task (used during shutdown)."""
        futures = [f for f in self._task_futures.values() if not f.done()]
        for f in futures:
            f.cancel()
        if futures:
            await asyncio.gather(*futures, return_exceptions=True)
        self._task_futures.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _next_id(self) -> str:
        self._counter += 1
        return f"sst-{self._counter}-{int(time.time() * 1000)}"

    def _get_symbol_lock(self, follower_id: str, symbol: str) -> asyncio.Lock:
        key = (follower_id, symbol)
        if key not in self._symbol_locks:
            self._symbol_locks[key] = asyncio.Lock()
        return self._symbol_locks[key]

    async def _broadcast_task(self, task: ShortSaleTask) -> None:
        await self._notifier.broadcast("short_sale_task_update", task.to_dict())

    def _task_done_callback(self, future: asyncio.Task[None]) -> None:
        if future.cancelled():
            return
        exc = future.exception()
        if exc is not None:
            logger.error(
                "Unhandled exception in short sale task: %s",
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    async def _execute_task(
        self,
        task: ShortSaleTask,
        master_order: BaseOrder,
        follower_config: dict[str, Any],
    ) -> None:
        """Core workflow: check capacity → locate deficit → place order."""
        lock = self._get_symbol_lock(task.follower_id, task.symbol)

        try:
            async with lock:
                await self._execute_task_locked(task, master_order, follower_config)
        except asyncio.CancelledError:
            task.status = "cancelled"
            logger.info("Short sale task %s cancelled", task.id)
            await self._broadcast_task(task)
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            logger.error("Short sale task %s failed: %s", task.id, e)
            await self._broadcast_task(task)
            await self._notifier.broadcast(
                "alert",
                {
                    "level": "error",
                    "message": (
                        f"Short sale failed for {task.symbol}"
                        f" on {task.follower_id}: {e}"
                    ),
                },
            )
        finally:
            self._task_futures.pop(task.id, None)

    async def _execute_task_locked(
        self,
        task: ShortSaleTask,
        master_order: BaseOrder,
        follower_config: dict[str, Any],
    ) -> None:
        """Runs inside the per-(follower, symbol) lock."""
        # --- Check cancellation ---
        if task.master_order_id in self._cancelled_master_orders:
            task.status = "cancelled"
            task.error = "Master order cancelled before execution"
            await self._broadcast_task(task)
            return

        # --- Check capacity ---
        task.status = "checking"
        await self._broadcast_task(task)

        client = self._das.get_connected_follower(task.follower_id)
        if not client:
            task.status = "failed"
            task.error = "Follower not connected"
            await self._broadcast_task(task)
            return

        max_sell = client.get_max_sell(task.symbol)
        deficit = task.required_qty - max_sell

        logger.info(
            "Short sale task %s capacity check: symbol=%s max_sell=%d "
            "required=%d deficit=%d",
            task.id,
            task.symbol,
            max_sell,
            task.required_qty,
            max(deficit, 0),
        )

        # --- Locate if needed ---
        if deficit > 0:
            task.locate_deficit = deficit
            task.status = "locating"
            await self._broadcast_task(task)

            max_price = Decimal(str(follower_config.get("max_locate_price", 0.10)))
            timeout = float(follower_config.get("locate_retry_timeout", 120))

            logger.info(
                "Short sale task %s locating %d shares of %s "
                "(max_price=$%s timeout=%ss)",
                task.id,
                deficit,
                task.symbol,
                max_price,
                timeout,
            )

            async with self._global_semaphore:
                # Re-check cancellation after potentially waiting on semaphore
                if task.master_order_id in self._cancelled_master_orders:
                    task.status = "cancelled"
                    task.error = "Master order cancelled while waiting"
                    await self._broadcast_task(task)
                    return

                result = await client.smart_locate(
                    symbol=task.symbol,
                    quantity=deficit,
                    max_price_per_share=max_price,
                    timeout=timeout,
                )

            if not result or result.filled_quantity < deficit:
                filled = result.filled_quantity if result else 0
                task.status = "failed"
                task.error = f"Locate incomplete: filled {filled}/{deficit} shares"
                logger.warning(
                    "Short sale task %s locate failed: %s",
                    task.id,
                    task.error,
                )
                await self._broadcast_task(task)
                await self._notifier.broadcast(
                    "alert",
                    {
                        "level": "warn",
                        "message": (
                            f"Could not locate {deficit} shares of"
                            f" {task.symbol} for {task.follower_id}"
                            f" (filled {filled})"
                        ),
                    },
                )
                return

            logger.info(
                "Short sale task %s located %d shares of %s",
                task.id,
                result.filled_quantity,
                task.symbol,
            )

        # --- Re-check cancellation before placing order ---
        if task.master_order_id in self._cancelled_master_orders:
            task.status = "cancelled"
            task.error = "Master order cancelled after locate"
            await self._broadcast_task(task)
            return

        # --- Place the order ---
        task.status = "placing_order"
        await self._broadcast_task(task)

        follower_oid = await self._order_replicator.replicate_order(
            master_order,
            task.follower_id,
            master_order_id=task.master_order_id,
        )

        if follower_oid is not None:
            task.status = "completed"
            task.follower_order_id = follower_oid
            logger.info(
                "Short sale task %s completed: follower_oid=%s",
                task.id,
                follower_oid,
            )
        else:
            task.status = "failed"
            task.error = "Order submission failed or was rejected"
            logger.warning(
                "Short sale task %s order placement failed",
                task.id,
            )

        await self._broadcast_task(task)
