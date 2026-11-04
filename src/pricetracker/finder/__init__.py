"""Find deals on unique items (artist jerseys, limited drops, vintage pieces)
by keyword search across marketplaces, judged against eBay sold prices.

Uses official APIs only: eBay Browse (+ Marketplace Insights for sold
prices, if your app is approved) and Etsy Open API v3.
"""

from .config import load_searches, make_spec
from .ebay import EbaySource
from .etsy import EtsySource
from .http import SourceError
from .models import FindResult, MarketListing, MarketValue, ScoredListing, SearchSpec, SoldComp
from .runner import Finder
from .seen import SeenStore

__all__ = ["Finder", "SearchSpec", "MarketListing", "MarketValue", "ScoredListing", "SoldComp",
           "FindResult", "EbaySource", "EtsySource", "SeenStore", "SourceError", "load_searches",
           "make_spec"]
