import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".weather-client.json"

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8000,
    "admin_token": "",
}


def load() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        if isinstance(data, dict):
            for k in DEFAULTS:
                if k in data:
                    merged[k] = data[k]
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def save(cfg: dict) -> None:
    payload = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except OSError:
        pass
