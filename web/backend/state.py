"""System state and in-memory log buffer for the web interface."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Log buffer — last 300 entries
# ---------------------------------------------------------------------------
_log_buffer: deque[dict[str, Any]] = deque(maxlen=300)

LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "WARN": 2, "WARNING": 2, "ERROR": 3}


def add_log(level: str, message: str, source: str = "system") -> None:
    """Append an entry to the in-memory log buffer."""
    _log_buffer.append(
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "level": level.upper(),
            "source": source,
            "message": message,
        }
    )


def get_logs(limit: int = 100, min_level: str = "DEBUG") -> list[dict[str, Any]]:
    """Return the *limit* most recent log entries at or above *min_level*."""
    threshold = LEVEL_ORDER.get(min_level.upper(), 0)
    filtered = [e for e in _log_buffer if LEVEL_ORDER.get(e["level"], 0) >= threshold]
    return filtered[-limit:]


def clear_logs() -> None:
    _log_buffer.clear()


# ---------------------------------------------------------------------------
# Chat history — last 100 exchanges
# ---------------------------------------------------------------------------
_history: deque[dict[str, Any]] = deque(maxlen=100)


def add_history(role: str, content: str, extra: dict | None = None) -> None:
    entry: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "role": role,
        "content": content,
    }
    if extra:
        entry.update(extra)
    _history.append(entry)


def get_history(limit: int = 50) -> list[dict[str, Any]]:
    return list(_history)[-limit:]


def clear_history() -> None:
    _history.clear()
