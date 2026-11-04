"""HTTP fetching, kept separate so tests can swap it out."""

from __future__ import annotations

from typing import Callable

import requests

# fetch(url) or fetch(url, headers={...}) -> page text
Fetcher = Callable[..., str]

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}


def http_fetch(url: str, headers: dict[str, str] | None = None, timeout: float = 20.0) -> str:
    """Download a page and return its HTML. Raises on HTTP errors."""
    resp = requests.get(url, headers={**DEFAULT_HEADERS, **(headers or {})}, timeout=timeout)
    resp.raise_for_status()
    return resp.text
