"""Tiny visitor stats: cumulative unique sessions ever seen, plus a sliding
window of currently-active sessions.

Persists `total_visits` and `seen_sessions` to a JSON file so deploys and
machine restarts don't reset the counter; the active set is in-memory only
(it's a 90-second window, so the cost of losing it on restart is one missed
sample for the admin page).

Not a full analytics product — just a counter the admin page reads.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Lock

_DATA_DIR = Path(os.environ.get("STATS_DATA_DIR", "/tmp/reelhouse-stats"))
_DATA_FILE = _DATA_DIR / "stats.json"

# Frontend beats every 30s. 90s covers one missed beacon (mobile suspend,
# brief network blip) without holding the session "active" forever after the
# tab closes.
_ACTIVE_TTL_SECONDS = 90.0

# Throttle disk writes — at most one save per N seconds even if many new
# sessions arrive in a burst.
_SAVE_DEBOUNCE_SECONDS = 5.0


class _Stats:
    def __init__(self) -> None:
        self._lock = Lock()
        self._total_visits: int = 0
        self._seen: set[str] = set()
        self._active: dict[str, float] = {}
        self._last_save: float = 0.0
        self._dirty: bool = False
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(_DATA_FILE.read_text())
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError):
            # Corrupt or unreadable — start fresh rather than crash startup.
            return
        self._total_visits = int(data.get("total_visits", 0))
        self._seen = set(data.get("seen_sessions", []))

    def _save_locked(self) -> None:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _DATA_FILE.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "total_visits": self._total_visits,
                    "seen_sessions": list(self._seen),
                }
            )
        )
        # Atomic on POSIX — the admin endpoint never sees a half-written file.
        tmp.replace(_DATA_FILE)
        self._last_save = time.monotonic()
        self._dirty = False

    def record_beat(self, sid: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._active[sid] = now
            if sid not in self._seen:
                self._seen.add(sid)
                self._total_visits += 1
                self._dirty = True
            if self._dirty and (now - self._last_save) >= _SAVE_DEBOUNCE_SECONDS:
                self._save_locked()

    def summary(self) -> dict[str, int]:
        now = time.monotonic()
        with self._lock:
            self._active = {
                s: t
                for s, t in self._active.items()
                if (now - t) <= _ACTIVE_TTL_SECONDS
            }
            return {
                "total_visits": self._total_visits,
                "active_now": len(self._active),
            }

    def flush(self) -> None:
        with self._lock:
            if self._dirty:
                self._save_locked()


_stats = _Stats()


def record_beat(sid: str) -> None:
    _stats.record_beat(sid)


def summary() -> dict[str, int]:
    return _stats.summary()


def flush() -> None:
    _stats.flush()
