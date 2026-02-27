"""Action queue for disconnected followers.

When a follower is disconnected at replication time, the action is queued here.
On reconnect the user is prompted to select which queued actions to replay.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class QueuedActionType(StrEnum):
    """Types of actions that can be queued for disconnected followers."""

    ORDER_SUBMIT = "order_submit"
    ORDER_CANCEL = "order_cancel"
    ORDER_REPLACE = "order_replace"


@dataclass
class QueuedAction:
    """A single action that was deferred because the follower was disconnected."""

    id: str  # uuid-style unique id
    follower_id: str
    action_type: QueuedActionType
    symbol: str
    timestamp: float = field(default_factory=time.time)

    # Payload differs by action_type;
    # ORDER_SUBMIT  → {"master_order_id": int}
    # ORDER_CANCEL  → {"master_order_id": int}
    # ORDER_REPLACE → {"master_order_id": int,
    #   "new_quantity": int|None, "new_price": str|None}
    payload: dict[str, Any] = field(default_factory=lambda: {})

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dictionary with serialized enum values."""
        d = asdict(self)
        d["action_type"] = self.action_type.value
        return d


class ActionQueue:
    """Per-follower queue of deferred actions."""

    def __init__(self) -> None:
        """Initialize an empty action queue."""
        # follower_id → list of queued actions (ordered by timestamp)
        self._queues: dict[str, list[QueuedAction]] = {}
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"qa-{self._counter}-{int(time.time() * 1000)}"

    # ---- enqueueing ----

    def enqueue(
        self,
        follower_id: str,
        action_type: QueuedActionType,
        symbol: str,
        payload: dict[str, Any] | None = None,
    ) -> QueuedAction:
        """Add an action to the queue for a follower."""
        action = QueuedAction(
            id=self._next_id(),
            follower_id=follower_id,
            action_type=action_type,
            symbol=symbol,
            payload=payload or {},
        )
        self._queues.setdefault(follower_id, []).append(action)
        logger.info(
            "Queued %s for follower %s: %s",
            action_type.value,
            follower_id,
            symbol,
        )
        return action

    # ---- retrieval ----

    def get_pending(self, follower_id: str) -> list[QueuedAction]:
        """Return all pending actions for a follower."""
        return list(self._queues.get(follower_id, []))

    def get_all_pending(self) -> dict[str, list[QueuedAction]]:
        """Return all pending actions grouped by follower ID."""
        return {fid: list(q) for fid, q in self._queues.items() if q}

    def has_pending(self, follower_id: str) -> bool:
        """Check if a follower has any pending queued actions."""
        return bool(self._queues.get(follower_id))

    # ---- removal ----

    def remove(self, follower_id: str, action_ids: set[str]) -> list[QueuedAction]:
        """Remove specific actions by their ids. Returns the removed actions."""
        if follower_id not in self._queues:
            return []
        removed = [a for a in self._queues[follower_id] if a.id in action_ids]
        self._queues[follower_id] = [
            a for a in self._queues[follower_id] if a.id not in action_ids
        ]
        return removed

    def clear(self, follower_id: str) -> list[QueuedAction]:
        """Clear all queued actions for a follower. Returns them."""
        return self._queues.pop(follower_id, [])

    def clear_all(self) -> None:
        """Clear all queued actions for every follower."""
        self._queues.clear()

    # ---- serialisation ----

    def pending_summary(self, follower_id: str) -> list[dict[str, Any]]:
        """Return serialized pending actions for a follower."""
        return [a.to_dict() for a in self.get_pending(follower_id)]
