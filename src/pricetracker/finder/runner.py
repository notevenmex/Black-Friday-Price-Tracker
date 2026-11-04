"""Run keyword searches across marketplaces and score what comes back."""

from __future__ import annotations

from typing import Protocol, Sequence

from .ebay import EbaySource
from .etsy import EtsySource
from .http import SourceError
from .models import FindResult, MarketListing, SearchSpec, SoldComp
from .scoring import is_relevant, market_value, rank, score
from .seen import SeenStore


class Source(Protocol):
    name: str
    label: str

    @property
    def configured(self) -> bool: ...

    def search(self, spec: SearchSpec, price_filter: bool = True) -> list[MarketListing]: ...


def default_sources() -> list[Source]:
    return [EbaySource(), EtsySource()]


class Finder:
    def __init__(self, sources: Sequence[Source] | None = None, seen: SeenStore | None = None):
        self.sources = list(sources) if sources is not None else default_sources()
        self.seen = seen
        # Set once eBay refuses sold-price lookups, so we don't ask every search.
        self.sold_unavailable: str | None = None

    @property
    def ebay(self) -> EbaySource | None:
        return next((s for s in self.sources if isinstance(s, EbaySource)), None)

    def _pick(self, spec: SearchSpec, result: FindResult) -> list[Source]:
        by_name = {s.name: s for s in self.sources}
        if spec.sites:
            picked = []
            for name in spec.sites:
                src = by_name.get(name)
                if src is None:
                    result.errors.append(f"Unknown site {name!r} (available: {', '.join(by_name)})")
                elif not src.configured:
                    try:
                        src.search(spec)  # raises SourceError explaining which key is missing
                    except SourceError as exc:
                        result.errors.append(f"{src.label}: {exc}")
                else:
                    picked.append(src)
            return picked
        picked = [s for s in self.sources if s.configured]
        if not picked:
            result.errors.append("No marketplace is set up. Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET "
                                 "(and optionally ETSY_API_KEY); see the README.")
        return picked

    def find(self, spec: SearchSpec) -> FindResult:
        result = FindResult(spec)
        listings: dict[tuple[str, str], MarketListing] = {}
        ebay_live: list[MarketListing] = []
        for src in self._pick(spec, result):
            try:
                found = src.search(spec)
            except SourceError as exc:
                result.errors.append(f"{src.label}: {exc}")
                continue
            except Exception as exc:  # network errors
                result.errors.append(f"{src.label}: {type(exc).__name__}: {exc}")
                continue
            if src is self.ebay:
                ebay_live = found
            for l in found:
                if is_relevant(l.title, spec):
                    listings.setdefault((l.site, l.listing_id), l)

        result.market = market_value(spec, self._sold(spec, result), self._asking(spec, ebay_live))
        scored = [score(l, spec, result.market) for l in listings.values()]
        if self.seen is not None:
            scored = self.seen.mark(spec, scored)
            if result.market is not None:
                self.seen.record_market(spec, result.market)
        result.listings = rank(scored)
        return result

    def _sold(self, spec: SearchSpec, result: FindResult) -> list[SoldComp]:
        ebay = self.ebay
        if spec.reference_price is not None or ebay is None or not ebay.configured or self.sold_unavailable:
            return []
        try:
            return ebay.sold(spec)
        except SourceError as exc:
            if exc.status in (401, 403, 404):
                self.sold_unavailable = ("eBay sold prices need Marketplace Insights API access "
                                         "(apply at https://developer.ebay.com/my/support/tickets); "
                                         "using live asking prices instead")
            else:
                result.errors.append(f"eBay sold prices: {exc}")
        except Exception as exc:
            result.errors.append(f"eBay sold prices: {type(exc).__name__}: {exc}")
        return []

    def _asking(self, spec: SearchSpec, ebay_live: list[MarketListing]) -> list[MarketListing]:
        """Live eBay asking prices across all prices (not just your budget)."""
        ebay = self.ebay
        if spec.reference_price is not None or ebay is None or not ebay.configured:
            return []
        if spec.min_price is None and spec.max_price is None:
            return ebay_live
        try:
            return ebay.search(spec, price_filter=False)
        except Exception:
            return []
