"""Etsy, through the official Open API v3 (no scraping).

Good for handmade, custom and vintage pieces. Create an app at
https://www.etsy.com/developers/your-apps and set its keystring:

    export ETSY_API_KEY=...
    export ETSY_SHARED_SECRET=...   # only if Etsy asks for "keystring:secret"

Etsy doesn't return shipping costs in search results, so totals are the item
price only. Not yet tested against the live API; parsing follows Etsy's
documented format and is covered by unit tests with a sample response.
"""

from __future__ import annotations

import html
import os
from decimal import Decimal

from .http import JsonClient, RequestsClient, SourceError
from .models import MarketListing, SearchSpec

SEARCH_URL = "https://openapi.etsy.com/v3/application/listings/active"


class EtsySource:
    name = "etsy"
    label = "Etsy"

    def __init__(self, client: JsonClient | None = None, api_key: str | None = None,
                 shared_secret: str | None = None, limit: int = 100):
        self.client = client or RequestsClient()
        self._key, self._secret = api_key, shared_secret
        self.limit = limit

    @property
    def api_key(self) -> str | None:
        key = self._key or os.environ.get("ETSY_API_KEY")
        secret = self._secret or os.environ.get("ETSY_SHARED_SECRET")
        if key and secret and ":" not in key:
            return f"{key}:{secret}"
        return key

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def search(self, spec: SearchSpec, price_filter: bool = True) -> list[MarketListing]:
        if not self.api_key:
            raise SourceError("Etsy needs an API key: set ETSY_API_KEY "
                              "(free at https://www.etsy.com/developers/your-apps)")
        params: dict = {"keywords": spec.keywords, "limit": self.limit, "sort_on": "score"}
        if price_filter and spec.min_price is not None:
            params["min_price"] = str(spec.min_price)
        if price_filter and spec.max_price is not None:
            params["max_price"] = str(spec.max_price)
        data = self.client.get(SEARCH_URL, params=params, headers={"x-api-key": self.api_key})
        listings = []
        for r in data.get("results") or []:
            money = r.get("price") or {}
            try:
                price = Decimal(money["amount"]) / Decimal(money.get("divisor") or 1)
            except (KeyError, TypeError, ArithmeticError):
                continue
            listings.append(MarketListing(
                site=self.name,
                listing_id=str(r.get("listing_id", "")),
                title=html.unescape(r.get("title", "")),
                price=price.quantize(Decimal("0.01")),
                currency=money.get("currency_code", "USD"),
                url=r.get("url"),
                buying_option="buy_it_now",
            ))
        return listings
