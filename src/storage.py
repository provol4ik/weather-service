import json
import logging
import threading
from pathlib import Path
from typing import Optional

from . import config

log = logging.getLogger(__name__)


def _key(city: str) -> str:
    return city.strip().lower()


class WeatherStorage:
    def __init__(self, cache_path: Path = config.CACHE_JSON):
        self._cache_path = cache_path
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}

    def set(self, city: str, data: dict) -> None:
        with self._lock:
            self._data[_key(city)] = data

    def get(self, city: str) -> Optional[dict]:
        with self._lock:
            return self._data.get(_key(city))

    def get_all(self) -> dict[str, dict]:
        with self._lock:
            return {k: dict(v) for k, v in self._data.items()}

    def delete(self, city: str) -> bool:
        with self._lock:
            return self._data.pop(_key(city), None) is not None

    def save_to_disk(self) -> None:
        with self._lock:
            snapshot = {k: dict(v) for k, v in self._data.items()}
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._cache_path.with_suffix(self._cache_path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            tmp.replace(self._cache_path)
            log.debug("Saved %d entries to %s", len(snapshot), self._cache_path)
        except OSError as exc:
            log.error("Failed to save cache: %s", exc)

    def load_from_disk(self) -> None:
        if not self._cache_path.exists():
            log.info("No cache file at %s — starting empty", self._cache_path)
            return
        try:
            with self._cache_path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                with self._lock:
                    self._data = {str(k): v for k, v in loaded.items() if isinstance(v, dict)}
                log.info("Loaded %d entries from cache", len(self._data))
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Failed to load cache: %s", exc)
