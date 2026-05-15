from typing import Optional
from urllib.parse import quote

import requests


class ClientError(Exception):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class WeatherClient:
    def __init__(self, host: str, port: int, admin_token: str = "", timeout: float = 10.0):
        self.host = host
        self.port = port
        self.admin_token = admin_token
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _headers(self) -> dict:
        if self.admin_token:
            return {"Authorization": f"Bearer {self.admin_token}"}
        return {}

    def _call(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        headers = self._headers()
        headers.update(kwargs.pop("headers", {}))
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise ClientError(f"Network error: {exc}") from exc

        if response.status_code >= 400:
            message = self._error_message(response)
            raise ClientError(message, status=response.status_code)

        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise ClientError(f"Invalid JSON response: {exc}") from exc

    @staticmethod
    def _error_message(response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict) and "error" in payload:
                return f"HTTP {response.status_code}: {payload['error']}"
        except ValueError:
            pass
        return f"HTTP {response.status_code}: {response.text[:200]}"

    def health(self) -> dict:
        return self._call("GET", "/health")

    def log(self, limit: Optional[int] = None) -> dict:
        params = {}
        if limit and limit > 0:
            params["limit"] = limit
        return self._call("GET", "/log", params=params)

    def cities_list(self) -> list:
        data = self._call("GET", "/cities")
        return data.get("cities", [])

    def cities_add(self, city: str, country: str = "") -> dict:
        return self._call("POST", "/cities", json={"city": city, "country": country})

    def cities_update(self, city: str, country: str) -> dict:
        return self._call("PUT", f"/cities/{quote(city)}", json={"country": country})

    def cities_delete(self, city: str) -> dict:
        return self._call("DELETE", f"/cities/{quote(city)}")

    def apis_list(self) -> dict:
        return self._call("GET", "/apis")

    def apis_add(self, key: str) -> dict:
        return self._call("POST", "/apis", json={"key": key})

    def apis_update(self, old: str, new: str) -> dict:
        return self._call("PUT", f"/apis/{quote(old)}", json={"key": new})

    def apis_delete(self, key: str) -> dict:
        return self._call("DELETE", f"/apis/{quote(key)}")

    def apis_reload(self) -> dict:
        return self._call("POST", "/apis/reload")
