import csv
import logging
import threading
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

FIELDS = ["city", "country"]


def _key(city: str) -> str:
    return city.strip().lower()


class CityManager:
    def __init__(self, csv_path: Path = config.CITIES_CSV):
        self._csv_path = csv_path
        self._lock = threading.Lock()
        self._cities: list[dict] = []
        self._index: set[str] = set()
        self._ensure_file()
        self.load_cities()

    def _ensure_file(self) -> None:
        if not self._csv_path.exists():
            self._csv_path.parent.mkdir(parents=True, exist_ok=True)
            with self._csv_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
            log.info("Created empty cities CSV at %s", self._csv_path)

    def _dump_all(self) -> None:
        self._csv_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._csv_path.with_suffix(self._csv_path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            for entry in self._cities:
                writer.writerow(entry)
        tmp.replace(self._csv_path)

    def load_cities(self) -> list[dict]:
        with self._lock:
            self._cities = []
            self._index = set()
            with self._csv_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    city = (row.get("city") or "").strip()
                    country = (row.get("country") or "").strip()
                    if not city:
                        continue
                    if _key(city) in self._index:
                        continue
                    self._cities.append({"city": city, "country": country})
                    self._index.add(_key(city))
            log.info("Loaded %d cities from %s", len(self._cities), self._csv_path)
            return list(self._cities)

    def list_cities(self) -> list[dict]:
        with self._lock:
            return list(self._cities)

    def city_exists(self, city: str) -> bool:
        with self._lock:
            return _key(city) in self._index

    def add_city(self, city: str, country: str = "") -> bool:
        city = (city or "").strip()
        country = (country or "").strip()
        if not city:
            raise ValueError("City name must not be empty")

        with self._lock:
            if _key(city) in self._index:
                return False
            entry = {"city": city, "country": country}
            self._cities.append(entry)
            self._index.add(_key(city))

            with self._csv_path.open("a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writerow(entry)

            log.info("Added new city: %s (%s)", city, country or "?")
            return True

    def update_city(self, city: str, new_country: str) -> bool:
        city = (city or "").strip()
        new_country = (new_country or "").strip()
        if not city:
            raise ValueError("City name must not be empty")

        with self._lock:
            target = _key(city)
            if target not in self._index:
                return False
            for entry in self._cities:
                if _key(entry["city"]) == target:
                    entry["country"] = new_country
                    break
            self._dump_all()
            log.info("Updated city: %s -> country=%s", city, new_country or "?")
            return True

    def delete_city(self, city: str) -> bool:
        city = (city or "").strip()
        if not city:
            raise ValueError("City name must not be empty")

        with self._lock:
            target = _key(city)
            if target not in self._index:
                return False
            self._cities = [e for e in self._cities if _key(e["city"]) != target]
            self._index.discard(target)
            self._dump_all()
            log.info("Deleted city: %s", city)
            return True
