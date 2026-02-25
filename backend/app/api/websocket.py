"""WebSocket endpoint for real-time UI updates."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.engine.replication_engine import ReplicationEngine
from app.services.notification_service import NotificationService

router = APIRouter()
logger = logging.getLogger(__name__)

# Injected at startup
_get_notifier: Callable[[], NotificationService] | None = None
_get_engine: Callable[[], ReplicationEngine] | None = None


def set_ws_dependencies(
    notifier_getter: Callable[[], NotificationService],
    engine_getter: Callable[[], ReplicationEngine],
) -> None:
    global _get_notifier, _get_engine
    _get_notifier = notifier_getter
    _get_engine = engine_getter


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Main WebSocket endpoint for real-time state push and user actions."""
    if _get_notifier is None:
        await ws.close(code=1011, reason="Server not initialized")
        return

    notifier = _get_notifier()
    await notifier.connect(ws)

    try:
        while True:
            # Listen for client messages (actions)
            data = await ws.receive_text()
            try:
                message = json.loads(data)
                await _handle_client_message(message)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from WebSocket client: %s", data[:100])
            except Exception as e:
                logger.error("Error handling WS message: %s", e)

    except WebSocketDisconnect:
        pass
    finally:
        await notifier.disconnect(ws)


async def _handle_client_message(message: dict[str, Any]) -> None:
    """Handle actions sent from the UI via WebSocket."""
    if _get_engine is None:
        return

    engine = _get_engine()
    action = message.get("action")

    if action == "accept_locate":
        locate_map_id = message.get("locate_map_id")
        if locate_map_id:
            await engine.locate_replicator.handle_user_accept(locate_map_id)

    elif action == "reject_locate":
        locate_map_id = message.get("locate_map_id")
        if locate_map_id:
            await engine.locate_replicator.handle_user_reject(locate_map_id)

    elif action == "override_multiplier":
        follower_id = message.get("follower_id")
        symbol = message.get("symbol")
        multiplier = message.get("multiplier")
        if follower_id and symbol and multiplier:
            await engine.multiplier_manager.set_symbol_override(
                follower_id, symbol.upper(), float(multiplier), source="user_override"
            )

    elif action == "replay_actions":
        follower_id = message.get("follower_id")
        action_ids = message.get("action_ids", [])
        if follower_id and action_ids:
            await engine.replay_queued_actions(follower_id, action_ids)

    elif action == "discard_actions":
        follower_id = message.get("follower_id")
        action_ids = message.get("action_ids", [])
        if follower_id and action_ids:
            await engine.discard_queued_actions(follower_id, action_ids)

    else:
        logger.warning("Unknown WebSocket action: %s", action)
