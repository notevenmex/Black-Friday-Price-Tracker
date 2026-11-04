"""Run price checks for a watchlist."""

from __future__ import annotations

import re
import time
from typing import Iterable

from .adapters import ExtractionError, get_adapter
from .fetch import Fetcher, http_fetch
from .models import SEARCH, PriceResult, WatchItem


def check_item(item: WatchItem, fetch: Fetcher | None = None) -> PriceResult:
    """Fetch one page and extract its price (or listings). Never raises."""
    fetch = fetch or http_fetch
    try:
        adapter = get_adapter(item.url, item.adapter)
        headers = adapter.request_headers()
        target = adapter.request_url(item.url)
        html = fetch(target, headers=headers) if headers else fetch(target)
        if item.kind == SEARCH:
            listings = tuple(adapter.extract_listings(html, item.url))
            priced = [l.price for l in listings if l.price is not None]
            if not priced:
                return PriceResult(item=item, price=None, listings=listings,
                                   error="No priced listings found")
            return PriceResult(item=item, price=min(priced), listings=listings,
                               title=f"{len(listings)} listings", source=adapter.name)
        found = adapter.extract(html, item.url)
    except ExtractionError as exc:
        return PriceResult(item=item, price=None, error=str(exc))
    except Exception as exc:  # network errors, unknown adapter, etc.
        return PriceResult(item=item, price=None, error=_redact(f"{type(exc).__name__}: {exc}"))
    return PriceResult(item=item, price=found.price, currency=found.currency, title=found.title,
                       source=adapter.name)


def check_all(
    items: Iterable[WatchItem],
    fetch: Fetcher | None = None,
    delay: float = 0.0,
) -> list[PriceResult]:
    """Check every item, pausing `delay` seconds between requests."""
    fetch = fetch or http_fetch
    results = []
    for i, item in enumerate(items):
        if i:
            try:
                wait = max(delay, get_adapter(item.url, item.adapter).min_delay)
            except KeyError:
                wait = delay
            if wait:
                time.sleep(wait)
        results.append(check_item(item, fetch))
    return results


_SECRET_PARAMS = re.compile(r"((?:api_?key|key|token)=)[^&\s]+", re.IGNORECASE)


def _redact(text: str) -> str:
    """Hide API keys that appear in request URLs inside error messages."""
    return _SECRET_PARAMS.sub(r"\1***", text)
