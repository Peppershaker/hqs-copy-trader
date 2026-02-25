"""Structured audit logging service.

Writes audit entries to the database for review and debugging.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.database import get_session_factory
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Writes structured audit log entries to the database."""

    async def log(
        self,
        level: str,
        category: str,
        message: str,
        *,
        follower_id: str | None = None,
        symbol: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Write an audit log entry."""
        try:
            factory = get_session_factory()
            async with factory() as session:
                entry = AuditLog(
                    level=level,
                    category=category,
                    follower_id=follower_id,
                    symbol=symbol,
                    message=message,
                    details=json.dumps(details) if details else None,
                )
                session.add(entry)
                await session.commit()
        except Exception as e:
            # Don't let audit failures break the app
            logger.error("Failed to write audit log: %s", e)

        # Also log to Python logger
        log_level = getattr(logging, level.upper(), logging.INFO)
        logger.log(log_level, "[%s] %s — %s", category, message, details or "")

    async def info(self, category: str, message: str, **kwargs: Any) -> None:
        await self.log("INFO", category, message, **kwargs)

    async def warn(self, category: str, message: str, **kwargs: Any) -> None:
        await self.log("WARN", category, message, **kwargs)

    async def error(self, category: str, message: str, **kwargs: Any) -> None:
        await self.log("ERROR", category, message, **kwargs)
