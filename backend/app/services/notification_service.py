"""WebSocket notification service.

Manages connected WebSocket clients and broadcasts state updates.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class NotificationService:
    """Manage WebSocket connections and broadcast messages."""

    def __init__(self) -> None:
        """Initialize with an empty connection list."""
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        """Register a new WebSocket connection."""
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
        logger.info("WebSocket client connected (%d total)", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)
        logger.info(
            "WebSocket client disconnected (%d remaining)", len(self._connections)
        )

    async def broadcast(
        self, msg_type: str, data: dict[str, Any] | None = None
    ) -> None:
        """Send a message to all connected WebSocket clients."""
        message = json.dumps({"type": msg_type, "data": data or {}})
        async with self._lock:
            dead: list[WebSocket] = []
            for ws in self._connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections.remove(ws)

    async def send_to(
        self, ws: WebSocket, msg_type: str, data: dict[str, Any] | None = None
    ) -> None:
        """Send a message to a specific WebSocket client."""
        message = json.dumps({"type": msg_type, "data": data or {}})
        try:
            await ws.send_text(message)
        except Exception:
            await self.disconnect(ws)

    @property
    def client_count(self) -> int:
        """Return the number of connected WebSocket clients."""
        return len(self._connections)
