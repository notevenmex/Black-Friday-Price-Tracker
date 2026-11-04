"""The tracker's features as plain functions that return Markdown text.

These back the MCP server (`pricetracker-mcp`), which lets Claude run the
tracker for you: "find Travis Scott jerseys under $120", "add this Best Buy
link to my watchlist", "how has the PS5 price moved?". They never print,
because an MCP stdio server must keep stdout for the protocol.

Files live in one folder, `~/.pricetracker` unless PRICETRACKER_HOME is set:

    watchlist.toml   products and saved searches (PRICETRACKER_WATCHLIST)
    prices.db        price history and seen listings (PRICETRACKER_DB)
    dashboard.html, finds.html
"""

from __future__ import annotations

import io
import json
import os
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from .adapters import get_adapter
from .checker import check_all
from .dashboard import write_dashboard
from .finder import Finder, SeenStore, load_searches, make_spec
from .finder.models import FindResult, ScoredListing
from .finder.report import SITE_LABELS, VERDICT_TEXT, market_line, money, pct, write_html
from .models import PRODUCT, SEARCH
from .sinks import ConsoleSink
from .store import PriceStore, PriceStoreSink
from .watchlist import WatchlistError, load_watchlist

WATCHLIST_HEADER = """# Price tracker watchlist. Edit by hand or ask Claude to add things.
# [[item]] = a product page (or a Craigslist/Facebook search) with a target price.
# [[search]] = a keyword search on eBay/Etsy for unique items.
# See watchlist.example.toml in the repository for every option.
"""


@dataclass(frozen=True)
class Paths:
    home: Path
    watchlist: Path
    db: Path

    @classmethod
    def from_env(cls) -> "Paths":
        home = Path(os.environ.get("PRICETRACKER_HOME") or Path.home() / ".pricetracker").expanduser()
        watchlist = Path(os.environ.get("PRICETRACKER_WATCHLIST") or home / "watchlist.toml").expanduser()
        db = Path(os.environ.get("PRICETRACKER_DB") or home / "prices.db").expanduser()
        return cls(home, watchlist, db)

    def ensure(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.db.parent.mkdir(parents=True, exist_ok=True)
        if not self.watchlist.exists():
            self.watchlist.parent.mkdir(parents=True, exist_ok=True)
            self.watchlist.write_text(WATCHLIST_HEADER, encoding="utf-8")


def _open(path: Path) -> None:
    try:
        webbrowser.open(path.resolve().as_uri())
    except Exception:
        pass


# --- finding deals on unique items ----------------------------------------

def _listing_md(i: int, s: ScoredListing, show_new: bool) -> str:
    l = s.listing
    price = money(l.price) if l.currency == "USD" else f"{l.price} {l.currency}"
    if l.shipping:
        price += f" + {money(l.shipping)} shipping"
    if l.buying_option == "auction":
        price += " (current bid" + (f", ends {l.ends_at:%b %d %H:%M} UTC" if l.ends_at else "") + ")"
    tags = [VERDICT_TEXT[s.verdict]]
    if s.discount is not None:
        tags.insert(0, pct(s.discount))
    if s.is_deal:
        tags.insert(0, "**DEAL**")
    if show_new and s.is_new:
        tags.append("new since last search")
    title = f"[{l.title}]({l.url})" if l.url else l.title
    extra = ", ".join(x for x in (SITE_LABELS.get(l.site, l.site), l.condition, l.seller and f"seller {l.seller}") if x)
    return f"{i}. {price} · {' · '.join(tags)}\n   {title} ({extra})"


def _finds_md(results: Sequence[FindResult], limit: int, deals_only: bool, new_only: bool,
              notes: Sequence[str]) -> str:
    out = []
    for r in results:
        out.append(f"## {r.spec.name}\n{market_line(r.market)}")
        out += [f"- Error: {e}" for e in r.errors]
        show_new = any(not s.is_new for s in r.listings)
        shown = [s for s in r.listings if (not deals_only or s.is_deal) and (not new_only or s.is_new)]
        if not shown:
            out.append("No matching listings." if not r.listings else "Nothing new or nothing matching the filter.")
        out += [_listing_md(i, s, show_new) for i, s in enumerate(shown[:limit], 1)]
        if len(shown) > limit:
            out.append(f"...and {len(shown) - limit} more.")
        out.append(f"{len(r.deals)} deal(s) out of {len(r.listings)} matching listing(s).")
    out += [f"Note: {n}" for n in notes]
    return "\n\n".join(out)


def _run_finder(specs, paths: Paths, finder: Finder | None = None) -> tuple[list[FindResult], list[str]]:
    paths.ensure()
    seen = SeenStore(paths.db)
    try:
        finder = finder or Finder()
        finder.seen = seen
        results = [finder.find(spec) for spec in specs]
    finally:
        seen.close()
    return results, [finder.sold_unavailable] if finder.sold_unavailable else []


def find_deals(keywords: str, max_price: float | None = None, min_price: float | None = None,
               exclude: list[str] | None = None, sites: list[str] | None = None,
               condition: str | None = None, deal_threshold_percent: float | None = None,
               reference_price: float | None = None, limit: int = 15, open_page: bool = False,
               *, paths: Paths | None = None, finder: Finder | None = None) -> str:
    paths = paths or Paths.from_env()
    spec = make_spec(None, keywords, max_price=max_price, min_price=min_price, exclude=exclude,
                     sites=sites, condition=condition, deal_threshold=deal_threshold_percent,
                     reference_price=reference_price)
    results, notes = _run_finder([spec], paths, finder)
    text = _finds_md(results, limit, False, False, notes)
    if open_page:
        page = write_html(results, paths.home / "finds.html", notes=notes)
        _open(page)
        text += f"\n\nResults page with photos: {page}"
    return text


def run_saved_searches(new_only: bool = False, deals_only: bool = False, limit: int = 10,
                       open_page: bool = False, *, paths: Paths | None = None,
                       finder: Finder | None = None) -> str:
    paths = paths or Paths.from_env()
    paths.ensure()
    specs = load_searches(paths.watchlist)
    if not specs:
        return (f"No saved searches yet in {paths.watchlist}. "
                "Use add_saved_search to save one, e.g. keywords 'travis scott jersey'.")
    results, notes = _run_finder(specs, paths, finder)
    text = _finds_md(results, limit, deals_only, new_only, notes)
    if open_page:
        page = write_html(results, paths.home / "finds.html", notes=notes)
        _open(page)
        text += f"\n\nResults page with photos: {page}"
    return text


# --- products with a target price -----------------------------------------

def check_prices(deals_only: bool = False, delay: float = 2.0, *, paths: Paths | None = None,
                 fetch=None) -> str:
    paths = paths or Paths.from_env()
    paths.ensure()
    items = load_watchlist(paths.watchlist)
    if not items:
        return f"The watchlist has no products yet ({paths.watchlist}). Use add_watch_item to add one."
    results = check_all(items, fetch=fetch, delay=delay)
    store = PriceStore(paths.db)
    try:
        before = {r.item.url: store.stats(r.item.url, days=90) for r in results}
        PriceStoreSink(store).write(results)
    finally:
        store.close()
    buf = io.StringIO()
    ConsoleSink(stream=buf, deals_only=deals_only).write(results)
    lows = []
    for r in results:
        stats = before.get(r.item.url)
        if r.ok and r.item.kind == PRODUCT and stats and r.price <= stats["low"]:
            lows.append(f"- {r.item.name}: {r.price} is at or below its 90-day low ({stats['low']})")
    text = "```\n" + buf.getvalue().rstrip() + "\n```"
    if lows:
        text += "\n\nAt a 90-day low:\n" + "\n".join(lows)
    return text


def show_watchlist(*, paths: Paths | None = None) -> str:
    paths = paths or Paths.from_env()
    paths.ensure()
    items = load_watchlist(paths.watchlist)
    searches = load_searches(paths.watchlist)
    out = [f"Watchlist file: {paths.watchlist}"]
    out.append(f"\n## Products ({len(items)})")
    for item in items:
        try:
            adapter = get_adapter(item.url, item.adapter).name
        except KeyError:
            adapter = "unknown adapter"
        out.append(f"- {item.name}: target {money(item.target_price)} [{item.kind}, {adapter}]\n  {item.url}")
    out.append(f"\n## Saved searches ({len(searches)})")
    for s in searches:
        bits = [f"keywords \"{s.keywords}\""]
        if s.exclude:
            bits.append("excluding " + ", ".join(s.exclude))
        if s.max_price is not None:
            bits.append(f"max {money(s.max_price)}")
        bits.append(f"deal at {s.deal_threshold * 100:.0f}% under market")
        out.append(f"- {s.name}: " + "; ".join(bits))
    return "\n".join(out)


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)  # JSON strings are valid TOML basic strings


def _append(paths: Paths, table: str, fields: dict) -> None:
    paths.ensure()
    lines = [f"\n[[{table}]]"] + [f"{k} = {_toml_value(v)}" for k, v in fields.items() if v not in (None, [], "")]
    original = paths.watchlist.read_text(encoding="utf-8")
    paths.watchlist.write_text(original.rstrip("\n") + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    try:  # make sure the file still parses; roll back if not
        load_watchlist(paths.watchlist)
        load_searches(paths.watchlist)
    except WatchlistError:
        paths.watchlist.write_text(original, encoding="utf-8")
        raise


def add_saved_search(name: str, keywords: str, exclude: list[str] | None = None,
                     max_price: float | None = None, min_price: float | None = None,
                     deal_threshold_percent: float | None = None, reference_price: float | None = None,
                     condition: str | None = None, sites: list[str] | None = None,
                     *, paths: Paths | None = None) -> str:
    paths = paths or Paths.from_env()
    paths.ensure()
    if any(s.name.lower() == name.lower() for s in load_searches(paths.watchlist)):
        return f"A saved search called {name!r} already exists. Pick another name or edit {paths.watchlist}."
    make_spec(name, keywords, exclude=exclude, max_price=max_price, condition=condition,
              deal_threshold=deal_threshold_percent)  # validates before writing
    _append(paths, "search", {"name": name, "keywords": keywords, "exclude": exclude or [],
                              "max_price": max_price, "min_price": min_price,
                              "deal_threshold": deal_threshold_percent, "reference_price": reference_price,
                              "condition": condition, "sites": sites or []})
    return f"Saved search {name!r} added to {paths.watchlist}. Run run_saved_searches to check it."


def add_watch_item(name: str, url: str, target_price: float, kind: str = PRODUCT,
                   product: str | None = None, asin: str | None = None,
                   *, paths: Paths | None = None) -> str:
    paths = paths or Paths.from_env()
    paths.ensure()
    if kind not in (PRODUCT, SEARCH):
        return "kind must be 'product' (a product page) or 'search' (a Craigslist/Facebook search page)."
    if not url.startswith(("http://", "https://")):
        return "The URL must start with http:// or https://."
    if any(i.url == url for i in load_watchlist(paths.watchlist)):
        return f"That URL is already on the watchlist ({paths.watchlist})."
    _append(paths, "item", {"name": name, "url": url, "target_price": target_price,
                            "kind": None if kind == PRODUCT else kind, "product": product, "asin": asin})
    adapter = get_adapter(url).name
    return (f"Added {name!r} (target {money(Decimal(str(target_price)))}, read by the {adapter} adapter) "
            f"to {paths.watchlist}. Run check_prices to fetch its price now.")


def price_history(name: str, days: int = 90, *, paths: Paths | None = None) -> str:
    """History for a watchlist item (by name, product group or URL) or a saved search's market value."""
    paths = paths or Paths.from_env()
    paths.ensure()
    items = load_watchlist(paths.watchlist)
    needle = name.lower().strip()
    matches = [i for i in items if needle in (i.name.lower(), i.group.lower(), i.url.lower())] or \
              [i for i in items if needle in i.name.lower() or needle in i.group.lower()]
    keys = [(i.name, i.url) for i in matches]
    for s in load_searches(paths.watchlist):
        if needle in s.name.lower():
            keys.append((f"{s.name} (market value)", f"search:{s.name}"))
    if not keys:
        return f"Nothing on the watchlist matches {name!r}. Use show_watchlist to see names."
    store = PriceStore(paths.db)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    try:
        for label, url in keys:
            points = [p for p in store.history(url, since=since) if p.price is not None]
            if not points:
                out.append(f"## {label}\nNo prices recorded in the last {days} days yet.")
                continue
            prices = [p.price for p in points]
            lowest = min(points, key=lambda p: p.price)
            lines = [f"## {label}",
                     f"Now {money(points[-1].price)} ({points[-1].observed_at:%b %d}). "
                     f"{days}-day low {money(lowest.price)} on {lowest.observed_at:%b %d}, "
                     f"high {money(max(prices))}, {len(points)} price points."]
            daily: dict[str, Decimal] = {}
            for p in points:
                daily[f"{p.observed_at:%Y-%m-%d}"] = p.price  # last price of each day
            recent = list(daily.items())[-14:]
            lines.append("Recent daily prices: " + ", ".join(f"{d[5:]} {money(v)}" for d, v in recent))
            out.append("\n".join(lines))
    finally:
        store.close()
    return "\n\n".join(out)


def build_dashboard(open_in_browser: bool = True, *, paths: Paths | None = None) -> str:
    paths = paths or Paths.from_env()
    paths.ensure()
    items = load_watchlist(paths.watchlist)
    store = PriceStore(paths.db)
    try:
        out = write_dashboard(items, store, paths.home / "dashboard.html")
    finally:
        store.close()
    if open_in_browser:
        _open(out)
    return f"Dashboard written to {out}" + (" and opened in your browser." if open_in_browser else ".")
