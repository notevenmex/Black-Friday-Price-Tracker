"""MCP server: use the price tracker by chatting with Claude.

    pip install -e ".[claude]"
    pricetracker-mcp            # speaks MCP over stdio; Claude starts it for you

See "Use it from Claude" in the README for the Claude Desktop and Claude
Code setup. Each tool is a thin wrapper around `pricetracker.toolkit`.
"""

from __future__ import annotations

import sys
from typing import Callable

from . import toolkit
from .finder.http import SourceError
from .watchlist import WatchlistError

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    try:
        from mcp.server.fastmcp import FastMCP as _Server
    except ImportError:  # pragma: no cover
        _Server = None

INSTRUCTIONS = """\
Tools for a personal Black Friday price tracker.
- Unique or one-off items (artist jerseys, limited drops, vintage): use find_deals with keywords.
  It searches eBay and Etsy and compares each listing with the median eBay sold price.
  Suggest `exclude` words such as replica, custom, kids, youth to filter fakes and wrong sizes.
- Regular products with a fixed product page (Amazon, Best Buy, Walmart, Target, ...): add_watch_item
  with a target price, then check_prices. price_history shows how a price has moved.
- To check something regularly, save it with add_saved_search and run run_saved_searches
  (new_only=true shows only listings not seen before).
When listing results, keep the links, the price vs. market value, and any "Too cheap? Check it's real"
warning. Prices come from live sites and can change.
"""


def _safe(fn: Callable[..., str]) -> Callable[..., str]:
    """Turn expected errors into readable tool results instead of protocol errors."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> str:
        try:
            return fn(*args, **kwargs)
        except (WatchlistError, SourceError, ValueError) as exc:
            return f"Error: {exc}"

    return wrapper


def build_server():
    if _Server is None:
        raise RuntimeError('The MCP server needs the "mcp" package: pip install -e ".[claude]"')
    server = _Server("pricetracker", instructions=INSTRUCTIONS)

    @server.tool()
    @_safe
    def find_deals(keywords: str, max_price: float | None = None, min_price: float | None = None,
                   exclude: list[str] | None = None, sites: list[str] | None = None,
                   condition: str | None = None, deal_threshold_percent: float | None = None,
                   reference_price: float | None = None, limit: int = 15,
                   open_page: bool = False) -> str:
        """Search eBay and Etsy for an item by keywords and flag listings priced under market value.

        Market value is the median eBay sold price over 90 days (or the median asking price when
        sold data isn't available). Every keyword must appear in a listing's title.

        Args:
            keywords: what to search for, e.g. "travis scott cactus jack jersey"
            max_price: always flag listings whose price + shipping is at or under this
            min_price: ignore listings under this price
            exclude: words that rule a listing out, e.g. ["replica", "custom", "kids"]
            sites: limit to some of "ebay", "etsy" (default: all with API keys set)
            condition: "new" or "used"
            deal_threshold_percent: percent under market value that counts as a deal (default 25)
            reference_price: the user's own idea of market value; skips eBay sold prices
            limit: how many listings to return
            open_page: also open a results page with photos in the user's browser
        """
        return toolkit.find_deals(keywords, max_price, min_price, exclude, sites, condition,
                                  deal_threshold_percent, reference_price, limit, open_page)

    @server.tool()
    @_safe
    def run_saved_searches(new_only: bool = False, deals_only: bool = False, limit: int = 10,
                           open_page: bool = False) -> str:
        """Run every saved keyword search in the watchlist.

        Args:
            new_only: only show listings not seen in an earlier run
            deals_only: only show listings flagged as deals
            limit: listings per search
            open_page: also open a results page with photos in the user's browser
        """
        return toolkit.run_saved_searches(new_only, deals_only, limit, open_page)

    @server.tool()
    @_safe
    def add_saved_search(name: str, keywords: str, exclude: list[str] | None = None,
                         max_price: float | None = None, min_price: float | None = None,
                         deal_threshold_percent: float | None = None,
                         reference_price: float | None = None, condition: str | None = None,
                         sites: list[str] | None = None) -> str:
        """Save a keyword search (e.g. an artist jersey) so run_saved_searches checks it every time.

        Args:
            name: a short label, e.g. "Bad Bunny jersey"
            keywords: search words; all must appear in a listing title
            exclude: words that rule a listing out, e.g. ["replica", "kids"]
            max_price: always flag listings at or under this total
            min_price: ignore listings under this price
            deal_threshold_percent: percent under market value that counts as a deal (default 25)
            reference_price: the user's own idea of market value
            condition: "new" or "used"
            sites: some of "ebay", "etsy"
        """
        return toolkit.add_saved_search(name, keywords, exclude, max_price, min_price,
                                        deal_threshold_percent, reference_price, condition, sites)

    @server.tool()
    @_safe
    def add_watch_item(name: str, url: str, target_price: float, kind: str = "product",
                       product: str | None = None, asin: str | None = None) -> str:
        """Add a product page to the watchlist with a target price.

        Works with Amazon, Best Buy (needs BESTBUY_API_KEY), Walmart, Micro Center, Target and most
        other stores. kind="search" is for a Craigslist or Facebook Marketplace search page.

        Args:
            name: a label, e.g. "PS5 Slim (Target)"
            url: the product page URL
            target_price: flag the item when its price is at or below this
            kind: "product" (default) or "search"
            product: same product at several stores: give them the same product name to share a chart
            asin: Amazon ASIN, for Keepa price history
        """
        return toolkit.add_watch_item(name, url, target_price, kind, product, asin)

    @server.tool()
    @_safe
    def check_prices(deals_only: bool = False) -> str:
        """Fetch the current price of every product on the watchlist, record it, and compare
        it to the target price and the 90-day low. Takes a few seconds per item."""
        return toolkit.check_prices(deals_only)

    @server.tool()
    @_safe
    def show_watchlist() -> str:
        """List the products and saved searches on the watchlist."""
        return toolkit.show_watchlist()

    @server.tool()
    @_safe
    def price_history(name: str, days: int = 90) -> str:
        """Show how a watched product's price (or a saved search's market value) has moved.

        Args:
            name: item name, product group, URL, or saved search name (partial names work)
            days: how far back to look
        """
        return toolkit.price_history(name, days)

    @server.tool()
    @_safe
    def build_dashboard(open_in_browser: bool = True) -> str:
        """Write the HTML dashboard with price charts for every watched product and open it."""
        return toolkit.build_dashboard(open_in_browser)

    return server


def main() -> None:
    try:
        server = build_server()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
    server.run()


if __name__ == "__main__":
    main()
