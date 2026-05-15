import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any


MAX_BODY_CHARS = 2000


def _truncate(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_BODY_CHARS:
        return value[:MAX_BODY_CHARS] + f"...[truncated {len(value) - MAX_BODY_CHARS} chars]"
    return value


def mask_api_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}***{key[-4:]}"


class RequestLog:
    def __init__(self, capacity: int = 1000):
        self._lock = threading.Lock()
        self._entries: deque = deque(maxlen=capacity)
        self._capacity = capacity
        self._next_id = 1

    def add(self, kind: str, **fields: Any) -> int:
        ts = time.time()
        entry = {
            "ts": ts,
            "time": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "kind": kind,
        }
        for k, v in fields.items():
            entry[k] = _truncate(v)
        with self._lock:
            entry["id"] = self._next_id
            self._next_id += 1
            self._entries.append(entry)
            return entry["id"]

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._entries)

    def tail(self, n: int) -> list[dict]:
        with self._lock:
            if n <= 0:
                return []
            return list(self._entries)[-n:]

    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
