from .base import HistoryError, HistoryProvider
from .keepa import KeepaHistory

#: Providers tried, in order, by `pricetracker backfill`.
PROVIDERS: list[HistoryProvider] = [KeepaHistory()]

__all__ = ["HistoryError", "HistoryProvider", "KeepaHistory", "PROVIDERS"]
