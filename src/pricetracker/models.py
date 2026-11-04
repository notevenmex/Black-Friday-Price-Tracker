"""Core data types shared across the tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

PRODUCT = "product"
SEARCH = "search"


@dataclass(frozen=True)
class WatchItem:
    """Something to watch, as configured in the watchlist.

    kind="product": `url` is a single product page; alert when its price
    is at or below `target_price`.
    kind="search": `url` is a search results page (e.g. Craigslist); alert
    on every listing priced at or below `target_price`.
    """

    name: str
    url: str
    target_price: Decimal
    adapter: str | None = None
    kind: str = PRODUCT
    #: Groups the same product at several stores onto one dashboard chart.
    #: Defaults to `name`.
    product: str | None = None
    #: Optional product identifiers used by price-history services.
    asin: str | None = None
    upc: str | None = None

    @property
    def group(self) -> str:
        return self.product or self.name


@dataclass(frozen=True)
class Listing:
    """One result on a search/resale page."""

    title: str
    price: Decimal | None
    url: str | None = None
    location: str | None = None


@dataclass(frozen=True)
class PriceResult:
    """The outcome of checking one watch item."""

    item: WatchItem
    price: Decimal | None
    currency: str | None = None
    title: str | None = None
    error: str | None = None
    listings: tuple[Listing, ...] = ()
    #: Which adapter produced the price (e.g. "amazon", "bestbuy").
    source: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def ok(self) -> bool:
        return self.error is None and self.price is not None

    @property
    def is_deal(self) -> bool:
        """True when the current (or lowest listed) price is at or below the target."""
        return self.ok and self.price <= self.item.target_price  # type: ignore[operator]

    @property
    def savings(self) -> Decimal | None:
        """How far below the target the price is (negative if above)."""
        if not self.ok:
            return None
        return self.item.target_price - self.price  # type: ignore[operator]

    @property
    def deal_listings(self) -> list[Listing]:
        """Search listings priced at or below the target, cheapest first."""
        hits = [l for l in self.listings if l.price is not None and l.price <= self.item.target_price]
        return sorted(hits, key=lambda l: l.price)  # type: ignore[arg-type, return-value]


@dataclass(frozen=True)
class PricePoint:
    """One historical price observation, from any source."""

    observed_at: datetime
    price: Decimal | None  # None means out of stock / no offer at that time
    source: str
    currency: str | None = None
