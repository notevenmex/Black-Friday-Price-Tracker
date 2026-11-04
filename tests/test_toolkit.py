import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from pricetracker import toolkit
from pricetracker.finder import EbaySource, EtsySource, Finder
from pricetracker.finder.ebay import BROWSE_URL, EbayAuth, INSIGHTS_URL
from pricetracker.finder.etsy import SEARCH_URL as ETSY_URL
from pricetracker.models import PricePoint
from pricetracker.store import PriceStore
from pricetracker.toolkit import Paths
from pricetracker.watchlist import WatchlistError, load_watchlist

from test_finder import FakeClient


@pytest.fixture
def paths(tmp_path):
    return Paths(tmp_path, tmp_path / "watchlist.toml", tmp_path / "prices.db")


@pytest.fixture
def finder(fixture_text):
    load = lambda n: json.loads(fixture_text(n))
    client = FakeClient({BROWSE_URL: load("ebay_browse.json"), INSIGHTS_URL: load("ebay_sold.json"),
                         ETSY_URL: load("etsy_search.json")})
    return lambda: Finder([EbaySource(client, EbayAuth(client, "id", "secret")),
                           EtsySource(client, api_key="k")])


def test_paths_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PRICETRACKER_HOME", str(tmp_path))
    monkeypatch.setenv("PRICETRACKER_DB", str(tmp_path / "other.db"))
    p = Paths.from_env()
    assert p.watchlist == tmp_path / "watchlist.toml" and p.db == tmp_path / "other.db"


def test_find_deals_markdown(paths, finder):
    text = toolkit.find_deals("travis scott jersey", exclude=["replica", "custom"], max_price=120,
                              paths=paths, finder=finder())
    assert "## travis scott jersey" in text
    assert "Market value: $145.00" in text
    assert "1. $40.00 (current bid" in text
    assert "[Travis Scott Cactus Jack Houston Astros Jersey Size L](https://www.ebay.com/itm/1001)" in text
    assert "**DEAL**" in text and "REPLICA" not in text


def test_find_deals_writes_page(paths, finder, monkeypatch):
    opened = []
    monkeypatch.setattr(toolkit, "_open", opened.append)
    text = toolkit.find_deals("travis scott jersey", open_page=True, paths=paths, finder=finder())
    assert opened == [paths.home / "finds.html"] and "Results page with photos" in text


def test_saved_searches_round_trip(paths, finder):
    assert "No saved searches yet" in toolkit.run_saved_searches(paths=paths, finder=finder())
    msg = toolkit.add_saved_search("Travis jersey", 'travis scott "jersey"', exclude=["replica"],
                                   max_price=120, paths=paths)
    assert "added" in msg
    assert "already exists" in toolkit.add_saved_search("travis JERSEY", "x", paths=paths)
    first = toolkit.run_saved_searches(paths=paths, finder=finder())
    assert "## Travis jersey" in first
    again = toolkit.run_saved_searches(new_only=True, paths=paths, finder=finder())
    assert "Nothing new" in again
    listing = toolkit.show_watchlist(paths=paths)
    assert 'keywords "travis scott "jersey""' in listing and "excluding replica" in listing


def test_add_watch_item(paths):
    msg = toolkit.add_watch_item("PS5 (Best Buy)", "https://www.bestbuy.com/site/x/6560000.p?skuId=6560000",
                                 399.99, product="PS5", paths=paths)
    assert "bestbuy adapter" in msg
    items = load_watchlist(paths.watchlist)
    assert items[0].target_price == Decimal("399.99") and items[0].product == "PS5"
    assert "already on the watchlist" in toolkit.add_watch_item("dup", items[0].url, 1, paths=paths)
    assert "must start with" in toolkit.add_watch_item("bad", "ftp://x", 1, paths=paths)


def test_bad_values_roll_back(paths):
    paths.ensure()
    before = paths.watchlist.read_text()
    with pytest.raises(WatchlistError):
        toolkit.add_saved_search("x", "y", condition="mint", paths=paths)
    assert paths.watchlist.read_text() == before


def test_check_prices_and_history(paths, fixture_text):
    toolkit.add_watch_item("Mouse", "https://shop.example/m", 40, paths=paths)
    store = PriceStore(paths.db)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    store.add_points("https://shop.example/m", "Mouse", [PricePoint(week_ago, Decimal("45"), "keepa", "USD")])
    store.close()
    text = toolkit.check_prices(delay=0, paths=paths, fetch=lambda url: fixture_text("generic_meta.html"))
    assert "[DEAL ] Mouse: 39.95" in text and "90-day low" in text
    hist = toolkit.price_history("mouse", paths=paths)
    assert "Now $39.95" in hist and "high $45.00" in hist
    assert "Nothing on the watchlist matches" in toolkit.price_history("tv", paths=paths)


def test_build_dashboard(paths):
    assert "dashboard.html" in toolkit.build_dashboard(open_in_browser=False, paths=paths)
    assert (paths.home / "dashboard.html").exists()


def test_mcp_server_registers_tools():
    pytest.importorskip("mcp")
    import asyncio

    from pricetracker.mcp_server import build_server

    names = {t.name for t in asyncio.run(build_server().list_tools())}
    assert {"find_deals", "add_saved_search", "run_saved_searches", "add_watch_item", "check_prices",
            "show_watchlist", "price_history", "build_dashboard"} <= names
