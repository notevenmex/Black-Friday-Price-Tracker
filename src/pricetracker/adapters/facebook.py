"""Facebook Marketplace listing and search pages.

Marketplace pages embed their data as JSON inside <script> tags. This
adapter walks that JSON for listing objects (they carry
`marketplace_listing_title` and `listing_price`), so it works on both a
single item page (`/marketplace/item/<id>`) and a search page
(`/marketplace/<city>/search?query=...`, used with `kind = "search"`).

Facebook shows less to logged-out visitors and often redirects to a login
page. To check while logged in, copy the `Cookie` header from your
browser's dev tools while on facebook.com and set it in the environment:

    export FACEBOOK_COOKIE='c_user=...; xs=...; ...'

Facebook's terms forbid automated access, so using your cookie puts that
account at risk of being restricted. Facebook also changes its page data
often; this adapter has not been checked against the live site yet, so
expect to adjust it after the first real run.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Listing
from ..prices import parse_price
from .base import Adapter, Extracted, ExtractionError

BASE = "https://www.facebook.com"


class FacebookMarketplaceAdapter(Adapter):
    name = "facebook"
    domains = ("facebook.com",)
    min_delay = 10.0

    def request_headers(self) -> dict[str, str]:
        cookie = os.environ.get("FACEBOOK_COOKIE")
        return {"Cookie": cookie} if cookie else {}

    def extract(self, html: str, url: str) -> Extracted:
        _check_login_wall(html)
        item_id = _item_id(url)
        listings = list(_listing_nodes(html))
        node = next((n for n in listings if item_id and str(n.get("id")) == item_id), None)
        node = node or next((n for n in listings if _price_of(n) is not None), None)
        if node is None:
            raise ExtractionError("Could not find listing data on the Marketplace page")
        return Extracted(price=_price_of(node), currency=_currency_of(node),
                         title=node.get("marketplace_listing_title"))

    def extract_listings(self, html: str, url: str) -> list[Listing]:
        _check_login_wall(html)
        seen, out = set(), []
        for node in _listing_nodes(html):
            key = node.get("id") or node.get("marketplace_listing_title")
            if key in seen:
                continue
            seen.add(key)
            out.append(Listing(
                title=str(node.get("marketplace_listing_title", "")).strip(),
                price=_price_of(node),
                url=urljoin(BASE, f"/marketplace/item/{node['id']}/") if node.get("id") else None,
                location=_location_of(node),
            ))
        return out


def _check_login_wall(html: str) -> None:
    if "marketplace_listing_title" in html:
        return
    soup = BeautifulSoup(html, "html.parser")
    if soup.find("form", id="login_form") or soup.find("input", attrs={"name": "pass"}):
        raise ExtractionError("Facebook showed a login page. Set FACEBOOK_COOKIE (see adapters/facebook.py)")


def _item_id(url: str) -> str | None:
    m = re.search(r"/marketplace/item/(\d+)", url)
    return m.group(1) if m else None


def _json_blobs(html: str) -> Iterator[Any]:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        text = script.string
        if not text or "marketplace_listing_title" not in text:
            continue
        try:
            yield json.loads(text)
        except json.JSONDecodeError:
            continue


def _listing_nodes(html: str) -> Iterator[dict]:
    for blob in _json_blobs(html):
        stack = [blob]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if "marketplace_listing_title" in node:
                    yield node
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(reversed(node))


def _price_of(node: dict):
    price = node.get("listing_price") or {}
    if isinstance(price, dict):
        return parse_price(price.get("amount") or price.get("formatted_amount"))
    return parse_price(price)


def _currency_of(node: dict) -> str | None:
    price = node.get("listing_price") or {}
    return price.get("currency") if isinstance(price, dict) else None


def _location_of(node: dict) -> str | None:
    geo = ((node.get("location") or {}).get("reverse_geocode") or {})
    parts = [geo.get("city"), geo.get("state")]
    return ", ".join(p for p in parts if p) or None
