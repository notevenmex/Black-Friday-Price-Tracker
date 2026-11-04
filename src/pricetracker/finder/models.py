"""Data types for keyword searches across resale and marketplace sites."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True)
class SearchSpec:
    """A keyword search for a one-of-a-kind or hard-to-find item.

    Unlike a watchlist item there is no single product page: every site is
    searched for `keywords`, and each listing is judged against what the
    item actually sells for (eBay sold prices).
    """

    name: str
    keywords: str
    #: Words that disqualify a listing when they appear in its title
    #: (e.g. "replica", "kids", "custom").
    exclude: tuple[str, ...] = ()
    min_price: Decimal | None = None
    #: Always flag listings at or under this total price (price + shipping).
    max_price: Decimal | None = None
    #: Sites to search, by source name. Empty = every configured source.
    sites: tuple[str, ...] = ()
    #: "new", "used" or None for any condition.
    condition: str | None = None
    #: Flag listings at least this far below the market price (0.25 = 25%).
    deal_threshold: Decimal = Decimal("0.25")
    #: Your own idea of the market price; overrides eBay sold prices.
    reference_price: Decimal | None = None
    #: Require every keyword in the title ("all") or just one ("any").
    match: str = "all"


@dataclass(frozen=True)
class MarketListing:
    """One listing found on a marketplace."""

    site: str
    listing_id: str
    title: str
    price: Decimal
    currency: str = "USD"
    url: str | None = None
    shipping: Decimal | None = None  # None = unknown
    condition: str | None = None
    image_url: str | None = None
    seller: str | None = None
    #: "auction" listings show the current bid, which will usually go up.
    buying_option: str | None = None
    ends_at: datetime | None = None

    @property
    def total(self) -> Decimal:
        return self.price + (self.shipping or Decimal(0))


@dataclass(frozen=True)
class SoldComp:
    """One completed sale, used to estimate market value."""

    title: str
    price: Decimal
    sold_at: datetime | None = None
    currency: str = "USD"


@dataclass(frozen=True)
class MarketValue:
    """What an item usually sells for, and how sure we are."""

    price: Decimal
    #: "ebay-sold", "ebay-asking" (median of live asking prices, less reliable)
    #: or "manual" (set in the search's reference_price).
    basis: str
    sample_size: int = 0
    low: Decimal | None = None
    high: Decimal | None = None


GREAT, GOOD, FAIR, HIGH, SUSPICIOUS = "great", "good", "fair", "high", "suspicious"


@dataclass(frozen=True)
class ScoredListing:
    listing: MarketListing
    #: Fraction below market value (0.30 = 30% under); negative = over.
    discount: Decimal | None
    verdict: str
    is_deal: bool
    is_new: bool = True


@dataclass
class FindResult:
    spec: SearchSpec
    listings: list[ScoredListing] = field(default_factory=list)
    market: MarketValue | None = None
    errors: list[str] = field(default_factory=list)
    searched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def deals(self) -> list[ScoredListing]:
        return [s for s in self.listings if s.is_deal]
