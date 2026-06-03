"""Tiny in-process TTL cache. One restart wipes it; that's fine for personal/dev use."""
from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock
from typing import Any


class TTLCache:
    def __init__(self, maxsize: int = 1024, ttl_seconds: float = 3600) -> None:
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl
        expires_at = time.monotonic() + ttl
        with self._lock:
            self._data[key] = (expires_at, value)
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)
