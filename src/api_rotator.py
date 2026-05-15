import csv
import logging
import threading
from pathlib import Path

from . import config
from .request_log import mask_api_key

log = logging.getLogger(__name__)

FIELDS = ["api_key"]


class RateLimitExhausted(Exception):
    pass


class APIRotator:
    def __init__(self, csv_path: Path = config.APIS_CSV, requests_per_key: int = config.REQUESTS_PER_KEY):
        self._csv_path = csv_path
        self._limit = requests_per_key
        self._lock = threading.Lock()
        self._keys: list[str] = []
        self._counters: dict[str, int] = {}
        self._index = 0
        self.reload_from_csv()

    def _dump_csv(self) -> None:
        self._csv_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._csv_path.with_suffix(self._csv_path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            for key in self._keys:
                writer.writerow({"api_key": key})
        tmp.replace(self._csv_path)

    def _load_keys_from_csv(self) -> list[str]:
        keys: list[str] = []
        if not self._csv_path.exists():
            return keys
        with self._csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row.get("api_key") or "").strip()
                if key:
                    keys.append(key)
        return keys

    def _load_keys_from_env(self) -> list[str]:
        raw = (config.OWM_API_KEYS or "").strip()
        if not raw:
            return []
        return [k.strip() for k in raw.split(",") if k.strip()]

    def reload_from_csv(self) -> None:
        with self._lock:
            keys = self._load_keys_from_csv()
            seeded_from_env = False
            if not keys:
                env_keys = self._load_keys_from_env()
                if env_keys:
                    # dedup preserving order
                    seen: set[str] = set()
                    keys = [k for k in env_keys if not (k in seen or seen.add(k))]
                    seeded_from_env = True

            for key in keys:
                self._counters.setdefault(key, 0)
            for stale in list(self._counters.keys()):
                if stale not in keys:
                    del self._counters[stale]

            self._keys = keys
            if self._index >= len(self._keys):
                self._index = 0

            if seeded_from_env:
                self._dump_csv()
                log.info("Seeded %d API key(s) from OWM_API_KEYS env into %s", len(self._keys), self._csv_path)
            elif not self._keys:
                log.warning("No API keys found in %s and OWM_API_KEYS is empty", self._csv_path)
            else:
                log.info("Loaded %d API key(s) from %s", len(self._keys), self._csv_path)

    def get_key(self) -> str:
        with self._lock:
            if not self._keys:
                raise RateLimitExhausted("No API keys configured")

            n = len(self._keys)
            for _ in range(n):
                key = self._keys[self._index]
                used = self._counters.get(key, 0)
                if used < self._limit:
                    self._counters[key] = used + 1
                    return key
                self._index = (self._index + 1) % n

            raise RateLimitExhausted("All API keys reached their hourly limit")

    def reset_counters(self) -> None:
        with self._lock:
            for key in self._counters:
                self._counters[key] = 0
            self._index = 0
            log.info("API key counters reset")

    def stats(self) -> dict:
        with self._lock:
            return {
                "total_keys": len(self._keys),
                "limit_per_key": self._limit,
                "usage": dict(self._counters),
                "current_index": self._index,
            }

    def list_keys(self, reveal: bool = False) -> list[dict]:
        with self._lock:
            return [
                {
                    "key": key if reveal else mask_api_key(key),
                    "used": self._counters.get(key, 0),
                    "limit": self._limit,
                }
                for key in self._keys
            ]

    def add_key(self, key: str) -> bool:
        key = (key or "").strip()
        if not key:
            raise ValueError("API key must not be empty")

        with self._lock:
            if key in self._keys:
                return False
            self._keys.append(key)
            self._counters.setdefault(key, 0)
            self._dump_csv()
            log.info("Added API key %s", mask_api_key(key))
            return True

    def delete_key(self, key: str) -> bool:
        key = (key or "").strip()
        if not key:
            raise ValueError("API key must not be empty")

        with self._lock:
            if key not in self._keys:
                return False
            self._keys.remove(key)
            self._counters.pop(key, None)
            if self._keys:
                self._index = self._index % len(self._keys)
            else:
                self._index = 0
            self._dump_csv()
            log.info("Deleted API key %s", mask_api_key(key))
            return True

    def update_key(self, old: str, new: str) -> bool:
        old = (old or "").strip()
        new = (new or "").strip()
        if not old or not new:
            raise ValueError("Both old and new API keys are required")

        with self._lock:
            if old not in self._keys:
                return False
            if new != old and new in self._keys:
                raise ValueError("New API key already exists")
            idx = self._keys.index(old)
            self._keys[idx] = new
            used = self._counters.pop(old, 0)
            self._counters[new] = used
            self._dump_csv()
            log.info("Replaced API key %s -> %s", mask_api_key(old), mask_api_key(new))
            return True
