"""Daily restart scheduler.

Restarts the DAS service and replication engine at a configured time each day
to reset accumulated state (order maps, retry tasks, etc.).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.engine.replication_engine import ReplicationEngine
    from app.services.das_service import DASService

logger = logging.getLogger(__name__)

NY_TZ = ZoneInfo("America/New_York")
RESTART_HOUR = 3
RESTART_MINUTE = 0


def _seconds_until_next_restart() -> float:
    """Calculate seconds until the next 3:00 AM New York time."""
    now = datetime.now(NY_TZ)
    target = now.replace(
        hour=RESTART_HOUR,
        minute=RESTART_MINUTE,
        second=0,
        microsecond=0,
    )
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def daily_restart_loop(
    das_service: DASService,
    engine: ReplicationEngine,
) -> None:
    """Sleep until 3 AM ET each day, then restart the DAS service and engine.

    This task runs forever and should be started as an asyncio task
    during application lifespan. Cancel it on shutdown.
    """
    while True:
        wait_secs = _seconds_until_next_restart()
        next_restart = datetime.now(NY_TZ) + timedelta(seconds=wait_secs)
        logger.info(
            "Daily restart scheduled for %s (in %.0f seconds)",
            next_restart.strftime("%Y-%m-%d %H:%M %Z"),
            wait_secs,
        )

        try:
            await asyncio.sleep(wait_secs)
        except asyncio.CancelledError:
            logger.info("Daily restart scheduler cancelled")
            return

        logger.info("Starting daily restart...")
        try:
            # Capture follower configs before stopping
            follower_configs = engine._follower_configs

            await engine.stop()
            await das_service.stop()

            await das_service.start()
            await engine.start(follower_configs=follower_configs)

            logger.info("Daily restart completed successfully")
        except asyncio.CancelledError:
            logger.info("Daily restart interrupted by shutdown")
            return
        except Exception as e:
            logger.error("Daily restart failed: %s", e, exc_info=True)
            # Continue the loop — try again tomorrow
