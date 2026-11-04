"""Retailer adapters.

To support a new store, subclass `SelectorAdapter` (or `Adapter`), set
`name`, `domains` and the CSS selectors, and add an instance to `ADAPTERS`.
See amazon.py or bestbuy.py for short examples.
"""

from __future__ import annotations

from .amazon import AmazonAdapter
from .base import Adapter, Extracted, ExtractionError, SelectorAdapter
from .bestbuy import BestBuyAdapter
from .craigslist import CraigslistAdapter
from .facebook import FacebookMarketplaceAdapter
from .generic import GenericAdapter
from .microcenter import MicroCenterAdapter
from .walmart import WalmartAdapter

# Site-specific adapters first; the generic one is the fallback.
ADAPTERS: list[Adapter] = [
    AmazonAdapter(),
    BestBuyAdapter(),
    WalmartAdapter(),
    MicroCenterAdapter(),
    CraigslistAdapter(),
    FacebookMarketplaceAdapter(),
]
FALLBACK: Adapter = GenericAdapter()


def get_adapter(url: str, name: str | None = None) -> Adapter:
    """Pick an adapter by explicit name, else by the URL's domain."""
    if name:
        for adapter in [*ADAPTERS, FALLBACK]:
            if adapter.name == name:
                return adapter
        raise KeyError(f"Unknown adapter: {name!r}")
    for adapter in ADAPTERS:
        if adapter.matches(url):
            return adapter
    return FALLBACK


__all__ = ["Adapter", "SelectorAdapter", "Extracted", "ExtractionError", "ADAPTERS", "get_adapter"]
