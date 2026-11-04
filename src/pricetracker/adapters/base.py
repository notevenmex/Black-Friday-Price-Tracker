"""Adapter interface: one adapter knows how to read prices from one kind of site."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..models import Listing
from ..prices import parse_price


class ExtractionError(Exception):
    """Raised when an adapter cannot find a price on the page."""


@dataclass(frozen=True)
class Extracted:
    price: Decimal
    currency: str | None = None
    title: str | None = None


class Adapter(ABC):
    #: Short name used in the watchlist's `adapter` field.
    name: str = ""
    #: Hostnames (without "www.") this adapter handles automatically.
    domains: tuple[str, ...] = ()
    #: Minimum seconds between requests when this adapter is used.
    min_delay: float = 0.0

    def request_headers(self) -> dict[str, str]:
        """Extra HTTP headers for this site (e.g. a login cookie)."""
        return {}

    def request_url(self, url: str) -> str:
        """The URL to download for a watched `url` (an API endpoint, for example)."""
        return url

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        return any(host == d or host.endswith("." + d) for d in self.domains)

    @abstractmethod
    def extract(self, html: str, url: str) -> Extracted:
        """Return the price found on a product page, or raise ExtractionError."""

    def extract_listings(self, html: str, url: str) -> list[Listing]:
        """Return the listings on a search results page.

        Only adapters for marketplaces/resale sites implement this.
        """
        raise ExtractionError(f"The {self.name!r} adapter does not support search watches")


class SelectorAdapter(Adapter):
    """Adapter driven by CSS selectors, with structured-data fallback.

    Subclasses usually only set `name`, `domains`, `price_selectors` and
    `title_selectors`. If none of the selectors match, the page's JSON-LD /
    meta tags are tried via the generic adapter.
    """

    price_selectors: tuple[str, ...] = ()
    title_selectors: tuple[str, ...] = ()
    #: Attribute to read the price from instead of the element's text (e.g. "content").
    price_attr: str | None = None
    default_currency: str | None = None

    def blocked_reason(self, soup: BeautifulSoup) -> str | None:
        """Return a message if the page is a bot-check/CAPTCHA page."""
        return None

    def extract(self, html: str, url: str) -> Extracted:
        soup = BeautifulSoup(html, "html.parser")
        if reason := self.blocked_reason(soup):
            raise ExtractionError(reason)

        title = None
        for selector in self.title_selectors:
            if el := soup.select_one(selector):
                title = el.get_text(" ", strip=True)
                break

        for selector in self.price_selectors:
            el = soup.select_one(selector)
            if el is None:
                continue
            raw = el.get(self.price_attr) if self.price_attr else None
            text = raw or el.get_text()
            if (price := parse_price(text)) is not None:
                return Extracted(price=price, currency=guess_currency(text) or self.default_currency,
                                 title=title)

        from .generic import GenericAdapter  # local import avoids a cycle

        try:
            found = GenericAdapter().extract(html, url)
        except ExtractionError:
            raise ExtractionError(f"Could not find a price on the {self.name} page") from None
        return Extracted(found.price, found.currency or self.default_currency, title or found.title)


def guess_currency(text: str) -> str | None:
    text = text.strip()
    if text.startswith(("US$", "$")):
        return "USD"
    if text.startswith("£"):
        return "GBP"
    if "€" in text:
        return "EUR"
    return None
