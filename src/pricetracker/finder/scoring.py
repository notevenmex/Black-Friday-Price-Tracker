"""Decide which listings are relevant, what the item is worth, and which are deals."""

from __future__ import annotations

import re
from decimal import Decimal
from statistics import median
from typing import Iterable, Sequence

from .models import (FAIR, GOOD, GREAT, HIGH, SUSPICIOUS, MarketListing, MarketValue,
                     ScoredListing, SearchSpec, SoldComp)

#: Need at least this many comparable sales/listings to trust a market value.
MIN_COMPS = 3
#: A listing this far under market value is more likely fake, damaged,
#: mislabeled or a scam than a real bargain, so it's flagged for a closer look.
SUSPICIOUS_DISCOUNT = Decimal("0.60")
GOOD_DISCOUNT = Decimal("0.10")

_WORD = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower().replace("’", "'"))


def _contains(title_words: list[str], phrase: str) -> bool:
    """True if `phrase` (one or more words) appears in the title, in order."""
    target = _words(phrase)
    if not target:
        return False
    n = len(target)
    return any(title_words[i:i + n] == target for i in range(len(title_words) - n + 1))


def is_relevant(title: str, spec: SearchSpec) -> bool:
    """Keyword match on the title: every keyword (or any, with match="any")
    must appear, and no excluded word may. Marketplace search engines are
    loose; this keeps a "travis scott jersey" search from returning posters."""
    words = _words(title)
    if any(_contains(words, bad) for bad in spec.exclude):
        return False
    keywords = [w for w in _words(spec.keywords) if len(w) > 1 or w.isdigit()]
    if not keywords:
        return True
    hits = [k in words or (k.endswith("s") and k[:-1] in words) or k + "s" in words for k in keywords]
    return any(hits) if spec.match == "any" else all(hits)


def _trimmed(prices: Sequence[Decimal]) -> list[Decimal]:
    """Drop outliers (lots, parts-only, typos) far from the median."""
    if len(prices) < MIN_COMPS:
        return list(prices)
    mid = Decimal(str(median(prices)))
    return [p for p in prices if mid / 4 <= p <= mid * 4]


def market_value(spec: SearchSpec, sold: Iterable[SoldComp] = (),
                 asking: Iterable[MarketListing] = ()) -> MarketValue | None:
    """Best available estimate of what the item sells for.

    1. `reference_price` from the search, if you set one.
    2. Median eBay sold price over the last 90 days (relevant titles only).
    3. Median asking price of live Buy It Now listings. Asking prices run
       higher than sale prices, so deals measured this way are conservative.
    """
    if spec.reference_price is not None:
        return MarketValue(spec.reference_price, "manual")
    for basis, prices in (
        ("ebay-sold", [c.price for c in sold
                       if c.currency == "USD" and is_relevant(c.title, spec)]),
        ("ebay-asking", [l.total for l in asking if l.currency == "USD" and l.buying_option != "auction"
                         and is_relevant(l.title, spec)]),
    ):
        kept = _trimmed(prices)
        if len(kept) >= MIN_COMPS:
            return MarketValue(Decimal(str(median(kept))).quantize(Decimal("0.01")), basis,
                               len(kept), min(kept), max(kept))
    return None


def score(listing: MarketListing, spec: SearchSpec, market: MarketValue | None) -> ScoredListing:
    total = listing.total
    discount = None
    if market is not None and market.price > 0 and listing.currency == "USD":
        discount = ((market.price - total) / market.price).quantize(Decimal("0.001"))

    under_budget = spec.max_price is not None and total <= spec.max_price
    if discount is None:
        verdict = GOOD if under_budget else FAIR
    elif discount >= SUSPICIOUS_DISCOUNT and listing.buying_option != "auction":
        # (An auction's current bid is low because bidding isn't over, not a red flag.)
        verdict = SUSPICIOUS
    elif discount >= spec.deal_threshold:
        verdict = GREAT
    elif discount >= GOOD_DISCOUNT:
        verdict = GOOD
    elif discount >= 0:
        verdict = FAIR
    else:
        verdict = HIGH

    is_deal = under_budget or verdict in (GREAT, SUSPICIOUS)
    return ScoredListing(listing, discount, verdict, is_deal)


def rank(scored: Iterable[ScoredListing]) -> list[ScoredListing]:
    """Deals first, then biggest discount, then cheapest."""
    def key(s: ScoredListing):
        return (not s.is_deal, -(s.discount if s.discount is not None else Decimal(-99)), s.listing.total)

    return sorted(scored, key=key)
