"""Fallback adapter that reads standard structured data.

Many stores publish schema.org Product data as JSON-LD, or Open Graph /
microdata price tags, for search engines. This adapter reads those, so it
works on a lot of sites without any site-specific code.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from bs4 import BeautifulSoup

from ..prices import parse_price
from .base import Adapter, Extracted, ExtractionError


class GenericAdapter(Adapter):
    name = "generic"
    domains = ()

    def matches(self, url: str) -> bool:  # used only as a fallback
        return True

    def extract(self, html: str, url: str) -> Extracted:
        soup = BeautifulSoup(html, "html.parser")
        title = _page_title(soup)

        for product in _json_ld_products(soup):
            for offer in _as_list(product.get("offers")):
                if not isinstance(offer, dict):
                    continue
                raw = offer.get("price", offer.get("lowPrice"))
                price = parse_price(raw)
                if price is not None:
                    return Extracted(
                        price=price,
                        currency=offer.get("priceCurrency"),
                        title=product.get("name") or title,
                    )

        for prop in ("product:price:amount", "og:price:amount"):
            tag = soup.find("meta", attrs={"property": prop})
            if tag and (price := parse_price(tag.get("content"))) is not None:
                cur = soup.find("meta", attrs={"property": prop.replace("amount", "currency")})
                return Extracted(price, cur.get("content") if cur else None, title)

        tag = soup.find(attrs={"itemprop": "price"})
        if tag is not None:
            price = parse_price(tag.get("content") or tag.get_text())
            if price is not None:
                cur = soup.find(attrs={"itemprop": "priceCurrency"})
                return Extracted(price, cur.get("content") if cur else None, title)

        raise ExtractionError("No structured price data found on page")


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _json_ld_products(soup: BeautifulSoup) -> Iterator[dict]:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = _as_list(data)
        while stack:
            node = stack.pop(0)
            if not isinstance(node, dict):
                continue
            types = _as_list(node.get("@type"))
            if "Product" in types:
                yield node
            stack.extend(_as_list(node.get("@graph")))


def _page_title(soup: BeautifulSoup) -> str | None:
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return None
