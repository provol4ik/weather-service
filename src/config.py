import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))

CITIES_CSV = DATA_DIR / "cities.csv"
APIS_CSV = DATA_DIR / "apis.csv"
CACHE_JSON = DATA_DIR / "weather_cache.json"

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
REQUEST_TIMEOUT = 10

POLL_INTERVAL_HOURS = int(os.environ.get("POLL_INTERVAL_HOURS", 1))
REQUESTS_PER_KEY = int(os.environ.get("REQUESTS_PER_KEY", 50))
CACHE_SAVE_MINUTES = int(os.environ.get("CACHE_SAVE_MINUTES", 5))

SERVER_HOST = os.environ.get("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("SERVER_PORT", 8181))

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

OWM_API_KEYS = os.environ.get("OWM_API_KEYS", "")
