"""eBay, through its official APIs (no scraping).

Live listings come from the Browse API, which any developer account can use.
Sold prices come from the Marketplace Insights API, which eBay only opens to
approved apps; without it, market value falls back to the median asking
price of live Buy It Now listings (see `scoring.market_value`).

Create a production keyset at https://developer.ebay.com/my/keys and set:

    export EBAY_CLIENT_ID=...      # "App ID (Client ID)"
    export EBAY_CLIENT_SECRET=...  # "Cert ID (Client Secret)"

Not yet tested against the live API; requests and parsing follow eBay's
documented formats and are covered by unit tests with sample responses.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from .http import JsonClient, RequestsClient, SourceError
from .models import MarketListing, SearchSpec, SoldComp

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
INSIGHTS_URL = "https://api.ebay.com/buy/marketplace_insights/v1_beta/item_sales/search"
SCOPE_PUBLIC = "https://api.ebay.com/oauth/api_scope"
SCOPE_INSIGHTS = "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"
CONDITIONS = {"new": "NEW", "used": "USED"}


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _when(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


class EbayAuth:
    """Gets and caches application access tokens (client-credentials grant)."""

    def __init__(self, client: JsonClient, client_id: str | None = None, client_secret: str | None = None):
        self.client = client
        self._id, self._secret = client_id, client_secret
        self._tokens: dict[str, tuple[str, float]] = {}

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def client_id(self) -> str | None:
        return self._id or os.environ.get("EBAY_CLIENT_ID")

    @property
    def client_secret(self) -> str | None:
        return self._secret or os.environ.get("EBAY_CLIENT_SECRET")

    def token(self, scope: str = SCOPE_PUBLIC) -> str:
        if not self.configured:
            raise SourceError("eBay needs API keys: set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET "
                              "(free at https://developer.ebay.com/my/keys)")
        cached = self._tokens.get(scope)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        data = self.client.post_form(TOKEN_URL, {"grant_type": "client_credentials", "scope": scope},
                                     auth=(self.client_id, self.client_secret))
        token = data.get("access_token")
        if not token:
            raise SourceError("eBay did not return an access token")
        self._tokens[scope] = (token, time.time() + float(data.get("expires_in", 7200)))
        return token


def _price_filter(spec: SearchSpec) -> str | None:
    if spec.min_price is None and spec.max_price is None:
        return None
    low = "" if spec.min_price is None else str(spec.min_price)
    high = "" if spec.max_price is None else str(spec.max_price)
    return f"price:[{low}..{high}],priceCurrency:USD"


class EbaySource:
    """Live eBay listings from the Browse API."""

    name = "ebay"
    label = "eBay"

    def __init__(self, client: JsonClient | None = None, auth: EbayAuth | None = None,
                 marketplace: str = "EBAY_US", limit: int = 100):
        self.client = client or RequestsClient()
        self.auth = auth or EbayAuth(self.client)
        self.marketplace = marketplace
        self.limit = limit

    @property
    def configured(self) -> bool:
        return self.auth.configured

    def _headers(self, scope: str = SCOPE_PUBLIC) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.auth.token(scope)}",
                "X-EBAY-C-MARKETPLACE-ID": self.marketplace}

    def search(self, spec: SearchSpec, price_filter: bool = True) -> list[MarketListing]:
        """Search live listings. `price_filter=False` ignores min/max price,
        which is how live asking prices are gathered for market value."""
        filters = []
        if price_filter and (pf := _price_filter(spec)):
            filters.append(pf)
        if spec.condition in CONDITIONS:
            filters.append(f"conditions:{{{CONDITIONS[spec.condition]}}}")
        params = {"q": spec.keywords, "limit": self.limit}
        if filters:
            params["filter"] = ",".join(filters)
        data = self.client.get(BROWSE_URL, params=params, headers=self._headers())
        return [l for l in (self._parse(s) for s in data.get("itemSummaries") or []) if l]

    def _parse(self, item: dict) -> MarketListing | None:
        options = item.get("buyingOptions") or []
        auction = "AUCTION" in options and "FIXED_PRICE" not in options
        money = (item.get("currentBidPrice") if auction else None) or item.get("price") or {}
        price = _dec(money.get("value"))
        if price is None:
            return None
        shipping = None
        for opt in item.get("shippingOptions") or []:
            cost = _dec((opt.get("shippingCost") or {}).get("value"))
            if cost is not None:
                shipping = cost if shipping is None else min(shipping, cost)
        return MarketListing(
            site=self.name,
            listing_id=str(item.get("itemId", "")),
            title=item.get("title", ""),
            price=price,
            currency=money.get("currency", "USD"),
            url=item.get("itemWebUrl"),
            shipping=shipping,
            condition=item.get("condition"),
            image_url=(item.get("image") or {}).get("imageUrl"),
            seller=(item.get("seller") or {}).get("username"),
            buying_option="auction" if auction else "buy_it_now",
            ends_at=_when(item.get("itemEndDate")) if auction else None,
        )

    def sold(self, spec: SearchSpec, days: int = 90) -> list[SoldComp]:
        """Completed sales from the Marketplace Insights API (last `days` days).

        Raises SourceError with status 403 when the app isn't approved for it.
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        filters = [f"lastSoldDate:[{since}..]"]
        if spec.condition in CONDITIONS:
            filters.append(f"conditions:{{{CONDITIONS[spec.condition]}}}")
        params = {"q": spec.keywords, "limit": 200, "filter": ",".join(filters)}
        data = self.client.get(INSIGHTS_URL, params=params, headers=self._headers(SCOPE_INSIGHTS))
        comps = []
        for sale in data.get("itemSales") or []:
            money = sale.get("lastSoldPrice") or {}
            price = _dec(money.get("value"))
            if price is not None:
                comps.append(SoldComp(sale.get("title", ""), price, _when(sale.get("lastSoldDate")),
                                      money.get("currency", "USD")))
        return comps
