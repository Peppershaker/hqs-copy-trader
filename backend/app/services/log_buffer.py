"""Logging setup: in-memory ring buffer, file handlers, and configuration.

Captures Python log records into a thread-safe ring buffer, separated by source
(``app`` for das_auto_order logs, ``das_bridge`` for the DAS bridge library).
Disk logs are written to a per-run directory with separate files for each source.
"""

from __future__ import annotations

import logging
import pathlib
import threading
from collections import deque
from datetime import datetime
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


class _SourceFilter(logging.Filter):
    """Route log records by logger-name prefix."""

    def __init__(
        self, *, include_prefix: str = "", exclude_prefix: str = "",
    ) -> None:
        super().__init__()
        self._include = include_prefix
        self._exclude = exclude_prefix

    def filter(self, record: logging.LogRecord) -> bool:
        if self._include:
            return record.name.startswith(self._include)
        if self._exclude:
            return not record.name.startswith(self._exclude)
        return True


# Module-level singleton so it can be imported anywhere.
log_buffer = LogBuffer()

_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def configure_logging(level: str, log_base: pathlib.Path) -> None:
    """Set up all logging: console, in-memory buffer, and per-run disk files.

    *level* is a string like ``"DEBUG"`` or ``"INFO"``.
    *log_base* is the parent directory for run directories (e.g. ``backend/logs``).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(_LOG_FMT)

    # Console
    logging.basicConfig(level=log_level, format=_LOG_FMT)

    root = logging.getLogger()

    # In-memory buffer (for WebSocket streaming)
    buf_handler = LogBufferHandler(log_buffer)
    buf_handler.setFormatter(formatter)
    root.addHandler(buf_handler)

    # Per-run directory with separate files
    log_dir = log_base / datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir.mkdir(parents=True, exist_ok=True)

    app_handler = logging.FileHandler(log_dir / "app.log")
    app_handler.setLevel(log_level)
    app_handler.setFormatter(formatter)
    app_handler.addFilter(_SourceFilter(exclude_prefix="das_bridge"))
    root.addHandler(app_handler)

    bridge_handler = logging.FileHandler(log_dir / "das_bridge.log")
    bridge_handler.setLevel(log_level)
    bridge_handler.setFormatter(formatter)
    bridge_handler.addFilter(_SourceFilter(include_prefix="das_bridge"))
    root.addHandler(bridge_handler)
