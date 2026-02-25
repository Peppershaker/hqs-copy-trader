"""WebSocket message schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WSMessage(BaseModel):
    """Generic WebSocket message envelope."""

    type: str
    data: dict[str, Any] = {}
