"""Small JSON-over-HTTP client, kept separate so tests can swap it out."""

from __future__ import annotations

from typing import Any, Protocol


class SourceError(Exception):
    """A marketplace could not be searched (bad key, HTTP error, ...)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class JsonClient(Protocol):
    def get(self, url: str, params: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None) -> dict: ...

    def post_form(self, url: str, data: dict[str, str], auth: tuple[str, str] | None = None) -> dict: ...


class RequestsClient:
    """The real client, using `requests`."""

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def get(self, url, params=None, headers=None) -> dict:
        import requests

        resp = requests.get(url, params=params, headers=headers, timeout=self.timeout)
        return self._json(resp)

    def post_form(self, url, data, auth=None) -> dict:
        import requests

        resp = requests.post(url, data=data, auth=auth, timeout=self.timeout)
        return self._json(resp)

    @staticmethod
    def _json(resp) -> dict:
        if resp.status_code >= 400:
            detail = ""
            try:
                body = resp.json()
                errors = body.get("errors") or body.get("error_description") or body.get("error")
                if isinstance(errors, list) and errors:
                    detail = errors[0].get("message", "")
                elif errors:
                    detail = str(errors)
            except ValueError:
                pass
            raise SourceError(f"HTTP {resp.status_code}{': ' + detail if detail else ''}",
                              status=resp.status_code)
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceError("Response was not JSON") from exc
