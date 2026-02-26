"""In-memory log buffer with a custom logging handler.

Captures Python log records into a thread-safe ring buffer, separated by source
(``app`` for das_auto_order logs, ``das_bridge`` for the DAS bridge library).
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any


class LogBuffer:
    """Thread-safe ring buffer that stores recent log entries."""

    def __init__(self, max_entries: int = 2000) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=max_entries)
        self._lock = threading.Lock()
        self._seq = 0

    def append(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self._seq += 1
            entry["seq"] = self._seq
            self._entries.append(entry)

    def get_entries(
        self,
        *,
        source: str | None = None,
        since_seq: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Return entries, optionally filtered by source and sequence."""
        with self._lock:
            entries = list(self._entries)
        if source:
            entries = [e for e in entries if e["source"] == source]
        if since_seq:
            entries = [e for e in entries if e["seq"] > since_seq]
        return entries[-limit:]

    def get_new_entries(self, since_seq: int = 0) -> list[dict[str, Any]]:
        """Return all entries newer than *since_seq*."""
        with self._lock:
            return [e for e in self._entries if e["seq"] > since_seq]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @property
    def latest_seq(self) -> int:
        with self._lock:
            return self._seq


class LogBufferHandler(logging.Handler):
    """Logging handler that writes formatted records into a :class:`LogBuffer`."""

    DAS_BRIDGE_PREFIXES = ("das_bridge",)

    def __init__(self, buffer: LogBuffer) -> None:
        super().__init__()
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            source = (
                "das_bridge"
                if record.name.startswith(self.DAS_BRIDGE_PREFIXES)
                else "app"
            )
            self.buffer.append(
                {
                    "timestamp": record.created,
                    "level": record.levelname,
                    "source": source,
                    "logger": record.name,
                    "message": self.format(record),
                }
            )
        except Exception:
            self.handleError(record)


# Module-level singleton so it can be imported anywhere.
log_buffer = LogBuffer()
