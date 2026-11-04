"""Micro Center product pages.

Micro Center prices are store-specific. Add `?storeid=NNN` to the product
URL in your watchlist to check a particular store's price.
"""

from __future__ import annotations

from .base import SelectorAdapter


class MicroCenterAdapter(SelectorAdapter):
    name = "microcenter"
    domains = ("microcenter.com",)
    default_currency = "USD"
    title_selectors = (".product-header h1", "h1")
    price_selectors = ("#pricing", "[itemprop='price']", ".big-price")
    price_attr = "content"
