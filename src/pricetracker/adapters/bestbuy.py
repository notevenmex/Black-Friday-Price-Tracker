"""Best Buy, via the free official Best Buy Products API.

Get a key at https://developer.bestbuy.com and set it in the environment:

    export BESTBUY_API_KEY=your-key

Watch a normal Best Buy product URL (it must contain the SKU, e.g.
`.../6505727.p?skuId=6505727`); the adapter turns it into an API call and
reads the current sale price. No HTML scraping is done.
"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import quote

from ..prices import parse_price
from .base import Adapter, Extracted, ExtractionError

API_URL = "https://api.bestbuy.com/v1/products/{sku}.json?apiKey={key}&show=sku,name,salePrice,regularPrice,onSale"
_SKU_PATTERNS = (re.compile(r"[?&]skuId=(\d+)"), re.compile(r"/(\d{6,8})\.p\b"), re.compile(r"/sku/(\d+)"))


def sku_from_url(url: str) -> str | None:
    for pattern in _SKU_PATTERNS:
        if m := pattern.search(url):
            return m.group(1)
    return None


class BestBuyAdapter(Adapter):
    name = "bestbuy"
    domains = ("bestbuy.com",)

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    @property
    def api_key(self) -> str | None:
        return self._api_key or os.environ.get("BESTBUY_API_KEY")

    def request_url(self, url: str) -> str:
        if not self.api_key:
            raise ExtractionError("Best Buy needs a free API key: set BESTBUY_API_KEY "
                                  "(get one at https://developer.bestbuy.com)")
        sku = sku_from_url(url)
        if not sku:
            raise ExtractionError("Could not find a Best Buy SKU in the URL (expected skuId=... or /NNNNNNN.p)")
        return API_URL.format(sku=sku, key=quote(self.api_key))

    def extract(self, html: str, url: str) -> Extracted:
        try:
            data = json.loads(html)
        except json.JSONDecodeError as exc:
            raise ExtractionError("Best Buy API returned something that isn't JSON") from exc
        price = parse_price(data.get("salePrice", data.get("regularPrice")))
        if price is None:
            raise ExtractionError("Best Buy API response has no price")
        return Extracted(price=price, currency="USD", title=data.get("name"))
