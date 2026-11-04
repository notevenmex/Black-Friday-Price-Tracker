"""Amazon product pages.

Amazon does not publish JSON-LD prices, so this reads its price elements
directly. Amazon changes its markup often and may block automated requests
with a CAPTCHA; if checks start failing, update the selectors below first.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from .base import SelectorAdapter


class AmazonAdapter(SelectorAdapter):
    name = "amazon"
    domains = ("amazon.com", "amazon.ca", "amazon.co.uk", "amazon.de", "amazon.es", "amazon.com.mx")
    title_selectors = ("#productTitle",)
    price_selectors = (
        "#corePrice_feature_div .a-price .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
        "#apex_desktop .a-price .a-offscreen",
        "#priceblock_dealprice",
        "#priceblock_ourprice",
        ".a-price .a-offscreen",
    )

    def blocked_reason(self, soup: BeautifulSoup) -> str | None:
        if soup.find("form", action=lambda a: a and "validateCaptcha" in a):
            return "Amazon returned a CAPTCHA page (request was blocked)"
        return None
