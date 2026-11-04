"""History providers: services that sell past prices for a product.

A provider returns `PricePoint`s that go into the same `PriceStore` table
as our own live checks. To add one (ShopSavvy, Wayback Machine, ...),
implement `HistoryProvider` and register it in `history/__init__.py`.
"""

from __future__ import annotations

from typing import Protocol

from ..models import PricePoint, WatchItem


class HistoryError(Exception):
    pass


class HistoryProvider(Protocol):
    name: str

    def supports(self, item: WatchItem) -> bool:
        """True if this provider can look up history for the item."""
        ...

    def fetch_history(self, item: WatchItem) -> list[PricePoint]: ...
