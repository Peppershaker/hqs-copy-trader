"""Locate replicator.

Handles replicating short locates from master to followers, including:
- Price comparison and auto-accept
- SmartLocateManager retry loops
- User prompts for expensive/delayed locates
- Auto-blacklist on rejection
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from das_bridge import DASClient
from das_bridge.domain.short import LocateOffer

from app.database import get_session_factory
from app.engine.blacklist_manager import BlacklistManager
from app.engine.multiplier_manager import MultiplierManager
from app.models.locate_map import LocateMap
from app.services.notification_service import NotificationService

if TYPE_CHECKING:
    from app.services.das_service import DASService

logger = logging.getLogger(__name__)


class LocateReplicator:
    """Replicates short locates from master to follower accounts."""

    def __init__(
        self,
        das_service: DASService,
        multiplier_mgr: MultiplierManager,
        blacklist_mgr: BlacklistManager,
        notifier: NotificationService,
    ) -> None:
        self._das = das_service
        self._multiplier_mgr = multiplier_mgr
        self._blacklist_mgr = blacklist_mgr
        self._notifier = notifier

        # Active retry tasks: locate_map_id → asyncio.Task
        self._retry_tasks: dict[int, asyncio.Task[None]] = {}
        # Pending prompts: locate_map_id → prompt data
        self._pending_prompts: dict[int, dict[str, Any]] = {}

    def _get_follower(self, follower_id: str) -> DASClient | None:
        """Get a connected follower client, or None."""
        return self._das.get_connected_follower(follower_id)

    async def replicate_locate(
        self,
        symbol: str,
        master_qty: int,
        master_price: float,
        follower_id: str,
        follower_config: dict[str, Any],
    ) -> None:
        """Attempt to replicate a master's locate to a follower.

        1. Calculate target quantity using multiplier
        2. Scan locate prices on follower
        3. If within price delta → auto-accept
        4. If too expensive → prompt user
        5. If unavailable → start retry loop
        """
        if self._blacklist_mgr.is_blacklisted(follower_id, symbol):
            logger.debug(
                "Skipping locate for %s on %s: symbol is blacklisted",
                symbol, follower_id,
            )
            return

        follower_client = self._get_follower(follower_id)
        if not follower_client:
            return

        multiplier = self._multiplier_mgr.get_effective(follower_id, symbol)
        target_qty = round(master_qty * multiplier)
        max_delta = follower_config.get("max_locate_price_delta", 0.01)
        retry_timeout = follower_config.get("locate_retry_timeout", 300)
        auto_accept = follower_config.get("auto_accept_locates", False)

        # Create tracking record
        locate_map_id = await self._create_locate_record(
            follower_id=follower_id,
            symbol=symbol,
            master_qty=master_qty,
            target_qty=target_qty,
            master_price=master_price,
            status="scanning",
        )

        logger.info(
            "Scanning locates for %s on %s: target=%d (master=%d x%.2f)",
            symbol, follower_id, target_qty, master_qty, multiplier,
        )

        try:
            # Scan available prices
            scan_result = await follower_client.scan_locate_prices(
                symbol=symbol,
                quantity=target_qty,
                timeout=5.0,
            )

            if scan_result and scan_result.best_offer:
                cheapest = scan_result.best_offer
                follower_price = float(cheapest.price_per_share)
                price_diff = follower_price - master_price

                logger.debug(
                    "Locate scan for %s on %s: follower_price=%.4f "
                    "master_price=%.4f diff=%.4f max_delta=%.4f",
                    symbol, follower_id,
                    follower_price, master_price, price_diff, max_delta,
                )

                await self._update_locate_record(
                    locate_map_id, follower_price=follower_price
                )

                if price_diff <= max_delta:
                    # Auto-accept: price is within acceptable range
                    if auto_accept:
                        await self._accept_locate(
                            locate_map_id,
                            cheapest,
                            follower_id,
                            symbol,
                        )
                    else:
                        await self._prompt_user(
                            locate_map_id,
                            follower_id,
                            symbol,
                            target_qty,
                            master_price,
                            follower_price,
                            reason="within_delta",
                        )
                else:
                    # Price too high — prompt user
                    await self._prompt_user(
                        locate_map_id,
                        follower_id,
                        symbol,
                        target_qty,
                        master_price,
                        follower_price,
                        reason="price_exceeded",
                    )
            else:
                # No locates available — start retry loop
                logger.debug(
                    "No locates available for %s on %s — starting retry loop",
                    symbol, follower_id,
                )
                await self._start_retry(
                    locate_map_id,
                    follower_id,
                    symbol,
                    target_qty,
                    master_price,
                    max_delta,
                    retry_timeout,
                    auto_accept,
                )

        except Exception as e:
            await self._update_locate_status(locate_map_id, "failed")
            logger.error(
                "Locate scan failed for %s on %s: %s",
                symbol, follower_id, e,
            )

    async def _accept_locate(
        self,
        locate_map_id: int,
        offer: LocateOffer,
        follower_id: str,
        symbol: str,
    ) -> None:
        """Accept a locate offer on the follower."""
        follower_client = self._get_follower(follower_id)
        if not follower_client:
            await self._update_locate_status(locate_map_id, "failed")
            return
        try:
            result = await follower_client.accept_locate_offer(offer)  # noqa: F841
            await self._update_locate_status(locate_map_id, "accepted")
            logger.info(
                "Auto-accepted locate for %s on %s",
                symbol, follower_id,
            )
            await self._notifier.broadcast(
                "locate_accepted",
                {
                    "locate_map_id": locate_map_id,
                    "follower_id": follower_id,
                    "symbol": symbol,
                },
            )
        except Exception as e:
            await self._update_locate_status(locate_map_id, "failed")
            logger.error(
                "Failed to accept locate for %s on %s: %s",
                symbol, follower_id, e,
            )

    async def _prompt_user(
        self,
        locate_map_id: int,
        follower_id: str,
        symbol: str,
        qty: int,
        master_price: float,
        follower_price: float,
        reason: str,
    ) -> None:
        """Send a locate prompt to the UI for user decision."""
        await self._update_locate_status(locate_map_id, "prompted")
        self._pending_prompts[locate_map_id] = {
            "follower_id": follower_id,
            "symbol": symbol,
            "qty": qty,
            "master_price": master_price,
            "follower_price": follower_price,
        }
        await self._notifier.broadcast(
            "locate_prompt",
            {
                "locate_map_id": locate_map_id,
                "follower_id": follower_id,
                "symbol": symbol,
                "qty": qty,
                "master_price": master_price,
                "follower_price": follower_price,
                "reason": reason,
            },
        )

    async def _start_retry(
        self,
        locate_map_id: int,
        follower_id: str,
        symbol: str,
        target_qty: int,
        master_price: float,
        max_delta: float,
        timeout_seconds: int,
        auto_accept: bool,
    ) -> None:
        """Start a background retry loop using SmartLocateManager."""
        await self._update_locate_status(locate_map_id, "retrying")

        async def retry_loop() -> None:
            try:
                follower_client = self._get_follower(follower_id)
                if not follower_client:
                    await self._update_locate_status(locate_map_id, "failed")
                    return
                result = await follower_client.smart_locate(
                    symbol=symbol,
                    quantity=target_qty,
                    max_price_per_share=Decimal(str(master_price + max_delta)),
                    timeout=float(timeout_seconds),
                )

                if result and result.filled_quantity > 0:
                    # Locates found! Prompt the user
                    follower_price = (
                        float(result.average_price_per_share)
                        if result.average_price_per_share
                        else master_price
                    )
                    await self._prompt_user(
                        locate_map_id,
                        follower_id,
                        symbol,
                        target_qty,
                        master_price,
                        follower_price,
                        reason="found_after_retry",
                    )
                    await self._notifier.broadcast(
                        "locate_found",
                        {
                            "locate_map_id": locate_map_id,
                            "follower_id": follower_id,
                            "symbol": symbol,
                        },
                    )
                else:
                    # Timed out without finding locates
                    await self._update_locate_status(locate_map_id, "timed_out")
                    await self._notifier.broadcast(
                        "alert",
                        {
                            "level": "warn",
                            "message": f"Locate retry timed out for {symbol} on {follower_id}",
                        },
                    )
            except asyncio.CancelledError:
                await self._update_locate_status(locate_map_id, "cancelled")
            except Exception as e:
                await self._update_locate_status(locate_map_id, "failed")
                logger.error(
                    "Locate retry failed for %s on %s: %s",
                    symbol, follower_id, e,
                )
            finally:
                # Only remove if this task is still the registered one
                if self._retry_tasks.get(locate_map_id) is task:
                    del self._retry_tasks[locate_map_id]

        task = asyncio.create_task(retry_loop(), name=f"locate-retry-{locate_map_id}")
        self._retry_tasks[locate_map_id] = task

    async def handle_user_accept(self, locate_map_id: int) -> dict[str, Any]:
        """User accepted a locate prompt.

        Accept the locates, and tell the user to manually enter the position.
        """
        prompt = self._pending_prompts.pop(locate_map_id, None)
        if not prompt:
            return {"success": False, "error": "No pending prompt found"}

        await self._update_locate_status(locate_map_id, "accepted")
        logger.info(
            "User accepted locate for %s on %s",
            prompt["symbol"], prompt["follower_id"],
        )

        # Notify UI to tell user to manually enter the position
        await self._notifier.broadcast(
            "locate_accepted_manual_entry",
            {
                "locate_map_id": locate_map_id,
                "follower_id": prompt["follower_id"],
                "symbol": prompt["symbol"],
                "message": f"Locates secured for {prompt['symbol']} on {prompt['follower_id']}. "
                f"Please manually enter the position.",
            },
        )

        return {
            "success": True,
            "follower_id": prompt["follower_id"],
            "symbol": prompt["symbol"],
        }

    async def handle_user_reject(self, locate_map_id: int) -> dict[str, Any]:
        """User rejected a locate prompt.

        Auto-blacklist the symbol on the follower.
        """
        prompt = self._pending_prompts.pop(locate_map_id, None)
        if not prompt:
            return {"success": False, "error": "No pending prompt found"}

        # Cancel any retry task
        task = self._retry_tasks.pop(locate_map_id, None)
        if task:
            task.cancel()

        await self._update_locate_status(locate_map_id, "rejected")

        # Auto-blacklist
        await self._blacklist_mgr.add(
            prompt["follower_id"],
            prompt["symbol"],
            reason="locate_rejected",
        )

        logger.info(
            "User rejected locate for %s on %s — symbol blacklisted",
            prompt["symbol"], prompt["follower_id"],
        )

        await self._notifier.broadcast(
            "locate_rejected",
            {
                "locate_map_id": locate_map_id,
                "follower_id": prompt["follower_id"],
                "symbol": prompt["symbol"],
                "blacklisted": True,
            },
        )

        return {
            "success": True,
            "follower_id": prompt["follower_id"],
            "symbol": prompt["symbol"],
            "blacklisted": True,
        }

    async def cancel_all_retries(self) -> None:
        """Cancel all active retry tasks (used during shutdown)."""
        for task in self._retry_tasks.values():
            task.cancel()
        if self._retry_tasks:
            await asyncio.gather(*self._retry_tasks.values(), return_exceptions=True)
        self._retry_tasks.clear()

    # --- DB helpers ---

    async def _create_locate_record(self, **kwargs: Any) -> int:
        factory = get_session_factory()
        async with factory() as session:
            record = LocateMap(**kwargs)
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record.id

    async def _update_locate_status(self, locate_map_id: int, status: str) -> None:
        factory = get_session_factory()
        async with factory() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(LocateMap).where(LocateMap.id == locate_map_id)
            )
            record = result.scalar_one_or_none()
            if record:
                record.status = status
                await session.commit()

    async def _update_locate_record(self, locate_map_id: int, **kwargs: Any) -> None:
        factory = get_session_factory()
        async with factory() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(LocateMap).where(LocateMap.id == locate_map_id)
            )
            record = result.scalar_one_or_none()
            if record:
                for k, v in kwargs.items():
                    setattr(record, k, v)
                await session.commit()
