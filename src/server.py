import logging
import threading
import time
from functools import wraps

from flask import Flask, g, jsonify, request

from . import config
from .api_rotator import APIRotator, RateLimitExhausted
from .city_manager import CityManager
from .request_log import RequestLog
from .storage import WeatherStorage
from .weather_collector import (
    CityNotFound,
    WeatherFetchError,
    fetch_with_rotator,
)

log = logging.getLogger(__name__)


def _extract_bearer(header: str) -> str:
    if not header:
        return ""
    parts = header.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return ""


def create_app(
    storage: WeatherStorage,
    cities: CityManager,
    rotator: APIRotator,
    request_log: RequestLog,
) -> Flask:
    app = Flask(__name__)

    def is_admin() -> bool:
        if not config.ADMIN_TOKEN:
            return True
        return _extract_bearer(request.headers.get("Authorization", "")) == config.ADMIN_TOKEN

    def require_admin(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not is_admin():
                return jsonify({"error": "Unauthorized"}), 401
            return fn(*args, **kwargs)
        return wrapper

    _LOG_EXCLUDED_PATHS = {"/log", "/health"}

    def _should_log_request() -> bool:
        return request.path not in _LOG_EXCLUDED_PATHS

    @app.before_request
    def _log_client_request():
        if not _should_log_request():
            return
        g.req_started = time.monotonic()
        body = request.get_json(silent=True) if request.is_json else None
        request_log.add(
            "client_request",
            method=request.method,
            path=request.path,
            query=dict(request.args),
            body=body,
            remote=request.remote_addr,
        )

    @app.after_request
    def _log_client_response(response):
        if not _should_log_request():
            return response
        body = response.get_json(silent=True) if response.is_json else None
        elapsed_ms = None
        started = g.pop("req_started", None)
        if started is not None:
            elapsed_ms = int((time.monotonic() - started) * 1000)
        request_log.add(
            "client_response",
            method=request.method,
            path=request.path,
            status=response.status_code,
            body=body,
            elapsed_ms=elapsed_ms,
        )
        return response

    @app.get("/health")
    def health():
        return jsonify({
            "status": "ok",
            "cities_tracked": len(cities.list_cities()),
            "cached_entries": len(storage.get_all()),
            "api_keys": rotator.stats(),
            "log_entries": len(request_log),
            "log_capacity": request_log.capacity(),
            "admin_token_required": bool(config.ADMIN_TOKEN),
        })

    @app.get("/cities")
    def list_cities():
        return jsonify({"cities": cities.list_cities()})

    @app.post("/cities")
    def add_city():
        body = request.get_json(silent=True) or {}
        city = (body.get("city") or "").strip()
        country = (body.get("country") or "").strip()
        if not city:
            return jsonify({"error": "Field 'city' is required"}), 400

        try:
            added = cities.add_city(city, country)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if not added:
            return jsonify({"status": "exists", "city": city}), 200

        def _fetch_in_background() -> None:
            try:
                data = fetch_with_rotator(city, country, rotator, request_log=request_log)
                storage.set(city, data)
            except (CityNotFound, RateLimitExhausted, WeatherFetchError) as exc:
                log.warning("Background fetch for new city %r failed: %s", city, exc)

        threading.Thread(target=_fetch_in_background, daemon=True).start()
        return jsonify({"status": "added", "fetch": "scheduled"}), 201

    @app.put("/cities/<city>")
    def update_city(city: str):
        body = request.get_json(silent=True) or {}
        country = (body.get("country") or "").strip()
        try:
            updated = cities.update_city(city, country)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not updated:
            return jsonify({"error": "City not found"}), 404
        return jsonify({"status": "updated", "city": city, "country": country})

    @app.delete("/cities/<city>")
    def delete_city(city: str):
        try:
            removed = cities.delete_city(city)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not removed:
            return jsonify({"error": "City not found"}), 404
        storage.delete(city)
        return jsonify({"status": "deleted", "city": city})

    @app.get("/weather")
    def all_weather():
        return jsonify({"weather": storage.get_all()})

    @app.get("/weather/<city>")
    def city_weather(city: str):
        cached = storage.get(city)
        if cached is not None:
            return jsonify({"source": "cache", "weather": cached})

        country = request.args.get("country", "").strip()
        try:
            cities.add_city(city, country)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        try:
            data = fetch_with_rotator(city, country, rotator, request_log=request_log)
        except CityNotFound:
            return jsonify({"error": "City not found in OpenWeatherMap"}), 404
        except RateLimitExhausted:
            return jsonify({"error": "All API keys exhausted; retry later"}), 503
        except WeatherFetchError as exc:
            return jsonify({"error": str(exc)}), 502

        storage.set(city, data)
        return jsonify({"source": "live", "weather": data})

    @app.get("/log")
    def get_log():
        try:
            limit = int(request.args.get("limit", "0"))
        except ValueError:
            limit = 0
        entries = request_log.tail(limit) if limit > 0 else request_log.all()
        return jsonify({
            "count": len(entries),
            "total": len(request_log),
            "capacity": request_log.capacity(),
            "entries": entries,
        })

    @app.get("/apis")
    def list_apis():
        reveal = is_admin()
        return jsonify({"keys": rotator.list_keys(reveal=reveal), "revealed": reveal})

    @app.post("/apis")
    @require_admin
    def add_api():
        body = request.get_json(silent=True) or {}
        key = (body.get("key") or "").strip()
        if not key:
            return jsonify({"error": "Field 'key' is required"}), 400
        try:
            added = rotator.add_key(key)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not added:
            return jsonify({"status": "exists"}), 200
        return jsonify({"status": "added"}), 201

    @app.put("/apis/<old_key>")
    @require_admin
    def update_api(old_key: str):
        body = request.get_json(silent=True) or {}
        new_key = (body.get("key") or "").strip()
        if not new_key:
            return jsonify({"error": "Field 'key' is required"}), 400
        try:
            replaced = rotator.update_key(old_key, new_key)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not replaced:
            return jsonify({"error": "Key not found"}), 404
        return jsonify({"status": "updated"})

    @app.delete("/apis/<key>")
    @require_admin
    def delete_api(key: str):
        try:
            removed = rotator.delete_key(key)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not removed:
            return jsonify({"error": "Key not found"}), 404
        return jsonify({"status": "deleted"})

    @app.post("/apis/reload")
    @require_admin
    def reload_apis():
        rotator.reload_from_csv()
        return jsonify({"status": "reloaded", "total_keys": rotator.stats()["total_keys"]})

    return app
