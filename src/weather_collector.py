import logging
import time
from typing import Optional

import requests

from . import config
from .api_rotator import APIRotator, RateLimitExhausted
from .request_log import RequestLog, mask_api_key
from .storage import WeatherStorage

log = logging.getLogger(__name__)


class WeatherFetchError(Exception):
    pass


class CityNotFound(WeatherFetchError):
    pass


def fetch_weather(
    city: str,
    country: str,
    api_key: str,
    request_log: Optional[RequestLog] = None,
) -> dict:
    query = f"{city},{country}" if country else city
    params = {"q": query, "appid": api_key, "units": "metric"}

    if request_log is not None:
        request_log.add(
            "weather_request",
            url=config.OPENWEATHER_URL,
            params={"q": query, "appid": mask_api_key(api_key), "units": "metric"},
        )

    started = time.monotonic()
    try:
        response = requests.get(
            config.OPENWEATHER_URL,
            params=params,
            timeout=config.REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        if request_log is not None:
            request_log.add(
                "weather_response",
                url=config.OPENWEATHER_URL,
                query=query,
                error=str(exc),
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
        raise WeatherFetchError(f"Network error: {exc}") from exc

    if request_log is not None:
        request_log.add(
            "weather_response",
            url=config.OPENWEATHER_URL,
            query=query,
            status=response.status_code,
            body=response.text,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )

    if response.status_code == 404:
        raise CityNotFound(f"City not found: {query}")
    if response.status_code == 401:
        raise WeatherFetchError("Invalid API key")
    if response.status_code == 429:
        raise WeatherFetchError("Rate limited by OpenWeatherMap")
    if not response.ok:
        raise WeatherFetchError(f"HTTP {response.status_code}: {response.text[:200]}")

    payload = response.json()
    main = payload.get("main", {})
    wind = payload.get("wind", {})
    weather = (payload.get("weather") or [{}])[0]

    return {
        "city": city,
        "country": country or payload.get("sys", {}).get("country", ""),
        "temperature": main.get("temp"),
        "feels_like": main.get("feels_like"),
        "humidity": main.get("humidity"),
        "pressure": main.get("pressure"),
        "wind_speed": wind.get("speed"),
        "wind_deg": wind.get("deg"),
        "description": weather.get("description"),
        "icon": weather.get("icon"),
        "id": weather.get("id"),
        "fetched_at": int(time.time()),
    }


def fetch_with_rotator(
    city: str,
    country: str,
    rotator: APIRotator,
    request_log: Optional[RequestLog] = None,
) -> dict:
    last_error: Optional[Exception] = None
    for _ in range(max(1, rotator.stats()["total_keys"])):
        try:
            key = rotator.get_key()
        except RateLimitExhausted:
            raise
        try:
            return fetch_weather(city, country, key, request_log=request_log)
        except WeatherFetchError as exc:
            last_error = exc
            msg = str(exc).lower()
            if "invalid api key" in msg or "rate limited" in msg:
                log.warning("Key issue for %s: %s — trying next key", city, exc)
                continue
            raise
    if last_error:
        raise last_error
    raise WeatherFetchError("Unknown error fetching weather")


def collect_all(
    cities: list[dict],
    rotator: APIRotator,
    storage: WeatherStorage,
    request_log: Optional[RequestLog] = None,
) -> dict:
    success, failed = 0, 0
    for entry in cities:
        city = entry.get("city", "")
        country = entry.get("country", "")
        if not city:
            continue
        try:
            data = fetch_with_rotator(city, country, rotator, request_log=request_log)
            storage.set(city, data)
            success += 1
        except RateLimitExhausted:
            log.error("All API keys exhausted; aborting hourly poll early")
            break
        except CityNotFound:
            log.warning("City not found in OpenWeatherMap: %s", city)
            failed += 1
        except WeatherFetchError as exc:
            log.warning("Failed to fetch %s: %s", city, exc)
            failed += 1

    log.info("Poll complete: %d ok, %d failed", success, failed)
    return {"ok": success, "failed": failed}
