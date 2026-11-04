"""Walmart product pages.

Walmart pages carry the price in an itemprop="price" element and in
JSON-LD; the selectors cover the visible price, and the structured-data
fallback covers the rest. Walmart may serve a "Robot or human?" check.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from .base import SelectorAdapter


class WalmartAdapter(SelectorAdapter):
    name = "walmart"
    domains = ("walmart.com", "walmart.ca")
    default_currency = "USD"
    title_selectors = ('h1[itemprop="name"]', "#main-title", "h1")
    price_selectors = (
        '[itemprop="price"]',
        '[data-testid="price-wrap"] [aria-hidden="true"]',
    )

    def blocked_reason(self, soup: BeautifulSoup) -> str | None:
        title = soup.title.string if soup.title and soup.title.string else ""
        if "robot or human" in title.lower():
            return "Walmart returned a bot check page (request was blocked)"
        return None
