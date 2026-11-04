"""Craigslist listing and search pages.

- A single posting URL (".../d/some-item/1234567890.html") works as a
  normal product watch.
- A search URL ("https://<city>.craigslist.org/search/sss?query=rtx+4080")
  works as a `kind = "search"` watch and reports every listing at or below
  your target price.

Craigslist's terms of use forbid automated access, and it blocks IPs
that request too fast. Keep watches few and checks infrequent; the adapter
enforces at least `min_delay` seconds between requests.
"""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Listing
from ..prices import parse_price
from .base import SelectorAdapter


class CraigslistAdapter(SelectorAdapter):
    name = "craigslist"
    domains = ("craigslist.org",)
    default_currency = "USD"
    min_delay = 5.0
    title_selectors = ("#titletextonly", ".postingtitletext")
    price_selectors = (".postingtitletext .price", "span.price")

    def extract_listings(self, html: str, url: str) -> list[Listing]:
        soup = BeautifulSoup(html, "html.parser")
        listings = []
        # Craigslist serves a no-JavaScript version of results in these <li>s.
        for li in soup.select("li.cl-static-search-result, li.cl-search-result"):
            link = li.find("a", href=True)
            title_el = li.select_one(".title, .label, .posting-title")
            title = (title_el.get_text(" ", strip=True) if title_el else li.get("title")) or ""
            price_el = li.select_one(".price, .priceinfo")
            loc_el = li.select_one(".location, .meta .location")
            listings.append(
                Listing(
                    title=title.strip(),
                    price=parse_price(price_el.get_text()) if price_el else None,
                    url=urljoin(url, link["href"]) if link else None,
                    location=loc_el.get_text(" ", strip=True) if loc_el else None,
                )
            )
        return listings
