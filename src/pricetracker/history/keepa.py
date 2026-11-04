"""Amazon price history from the Keepa API (https://keepa.com/api-docs/).

Needs a paid Keepa API key in KEEPA_API_KEY. Each lookup costs one token.
Watchlist items need an `asin` (or an Amazon URL containing /dp/<ASIN>).

Not yet tested against the live API; the response parsing follows Keepa's
documented format and is covered by unit tests with a sample payload.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

from ..models import PricePoint, WatchItem
from .base import HistoryError

API_URL = "https://api.keepa.com/product"
# Keepa domain ids: 1 = amazon.com, 2 = .co.uk, 3 = .de, 6 = .ca, 9 = .es, 11 = .com.mx
DOMAIN_IDS = {"amazon.com": 1, "amazon.co.uk": 2, "amazon.de": 3, "amazon.ca": 6, "amazon.es": 9,
              "amazon.com.mx": 11}
# Indexes into Keepa's `csv` array.
CSV_AMAZON, CSV_NEW = 0, 1
_KEEPA_EPOCH_MINUTES = 21_564_000  # Keepa time is minutes since 2011-01-01
_ASIN_IN_URL = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})")

JsonGetter = Callable[[str, dict], dict]


def keepa_time(minutes: int) -> datetime:
    return datetime.fromtimestamp((minutes + _KEEPA_EPOCH_MINUTES) * 60, tz=timezone.utc)


def asin_for(item: WatchItem) -> str | None:
    if item.asin:
        return item.asin
    m = _ASIN_IN_URL.search(item.url)
    return m.group(1) if m else None


def _default_get(url: str, params: dict) -> dict:
    import requests

    resp = requests.get(url, params=params, timeout=60)
    if resp.status_code != 200:
        raise HistoryError(f"Keepa API returned HTTP {resp.status_code}")
    return resp.json()


def parse_series(series: list[int] | None, source: str, currency: str = "USD") -> list[PricePoint]:
    """Turn Keepa's flat [time, price, time, price, ...] list into points.

    Prices are in cents; -1 means no offer (out of stock).
    """
    if not series:
        return []
    points = []
    for t, cents in zip(series[0::2], series[1::2]):
        price = None if cents < 0 else Decimal(cents) / 100
        points.append(PricePoint(keepa_time(t), price, source, currency))
    return points


class KeepaHistory:
    name = "keepa"

    def __init__(self, api_key: str | None = None, get_json: JsonGetter = _default_get):
        self._api_key = api_key
        self.get_json = get_json

    @property
    def api_key(self) -> str | None:
        return self._api_key or os.environ.get("KEEPA_API_KEY")

    def supports(self, item: WatchItem) -> bool:
        return asin_for(item) is not None

    def fetch_history(self, item: WatchItem) -> list[PricePoint]:
        if not self.api_key:
            raise HistoryError("Set KEEPA_API_KEY to use Keepa history")
        asin = asin_for(item)
        if not asin:
            raise HistoryError(f"No ASIN for {item.name!r}")
        domain = next((v for k, v in DOMAIN_IDS.items() if f"{k}/" in item.url + "/"), 1)
        data = self.get_json(API_URL, {"key": self.api_key, "domain": domain, "asin": asin})
        if "error" in data:
            raise HistoryError(f"Keepa error: {json.dumps(data['error'])}")
        products = data.get("products") or []
        if not products:
            raise HistoryError(f"Keepa has no data for ASIN {asin}")
        csv = products[0].get("csv") or []
        currency = "USD" if domain == 1 else None
        # Prefer Amazon's own price; fall back to the lowest new third-party
        # offer for products Amazon doesn't sell itself. One series per
        # product keeps the dashboard to one line per store.
        amazon = parse_series(csv[CSV_AMAZON] if len(csv) > CSV_AMAZON else None, "keepa", currency)
        if any(p.price is not None for p in amazon):
            return amazon
        return parse_series(csv[CSV_NEW] if len(csv) > CSV_NEW else None, "keepa", currency)
