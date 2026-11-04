from decimal import Decimal

from pricetracker.adapters.bestbuy import BestBuyAdapter
from pricetracker.checker import check_all, check_item
from pricetracker.models import WatchItem


def item(url, target="100", **kw):
    return WatchItem(name="thing", url=url, target_price=Decimal(target), **kw)


def test_deal_found(fixture_text):
    result = check_item(item("https://www.amazon.com/dp/X", "130"), fetch=lambda u: fixture_text("amazon.html"))
    assert result.ok and result.is_deal
    assert result.savings == Decimal("5.01")
    assert result.source == "amazon"


def test_price_above_target(fixture_text):
    result = check_item(item("https://www.amazon.com/dp/X", "100"), fetch=lambda u: fixture_text("amazon.html"))
    assert result.ok and not result.is_deal


def test_network_error_is_captured():
    def boom(url):
        raise ConnectionError("down")

    result = check_item(item("https://www.amazon.com/dp/X"), fetch=boom)
    assert not result.ok
    assert "ConnectionError" in result.error


def test_api_keys_are_redacted_from_errors(monkeypatch):
    monkeypatch.setenv("BESTBUY_API_KEY", "supersecret")

    def boom(url):
        raise RuntimeError(f"404 for url: {url}")

    result = check_item(item("https://www.bestbuy.com/site/x/6505727.p"), fetch=boom)
    assert "supersecret" not in result.error
    assert "apiKey=***" in result.error


def test_bestbuy_fetches_api_url(monkeypatch, fixture_text):
    monkeypatch.setenv("BESTBUY_API_KEY", "k")
    seen = []

    def fake_fetch(url):
        seen.append(url)
        return fixture_text("bestbuy_api.json")

    result = check_item(item("https://www.bestbuy.com/site/x/6505727.p", "900"), fetch=fake_fetch)
    assert seen and seen[0].startswith("https://api.bestbuy.com/")
    assert result.is_deal and result.price == Decimal("899.99")


def test_search_watch_reports_deal_listings(fixture_text):
    url = "https://sfbay.craigslist.org/search/sss?query=rtx+4080"
    result = check_item(item(url, "700", kind="search"), fetch=lambda u: fixture_text("craigslist_search.html"))
    assert result.ok and result.is_deal
    assert result.price == Decimal("650")
    assert [l.title for l in result.deal_listings] == ["RTX 4080 Founders Edition"]


def test_search_watch_with_no_listings():
    url = "https://sfbay.craigslist.org/search/sss?query=nothing"
    result = check_item(item(url, kind="search"), fetch=lambda u: "<html></html>")
    assert not result.ok and "No priced listings" in result.error


def test_adapter_headers_are_passed_to_fetch(monkeypatch, fixture_text):
    monkeypatch.setenv("FACEBOOK_COOKIE", "c_user=1")
    seen = {}

    def fake_fetch(url, headers=None):
        seen["headers"] = headers
        return fixture_text("facebook_search.html")

    url = "https://www.facebook.com/marketplace/sf/search?query=ps5"
    result = check_item(item(url, "100", kind="search"), fetch=fake_fetch)
    assert seen["headers"] == {"Cookie": "c_user=1"}
    assert result.deal_listings[0].title == "PS5 controller"


def test_marketplace_sites_are_paced(monkeypatch, fixture_text):
    sleeps = []
    monkeypatch.setattr("pricetracker.checker.time.sleep", sleeps.append)
    urls = ["https://a.example", "https://sfbay.craigslist.org/search/sss?query=x"]
    check_all([item(u) for u in urls], fetch=lambda u: "", delay=1)
    assert sleeps == [5.0]


def test_check_all_keeps_order(fixture_text):
    pages = {"https://a.example": fixture_text("generic_meta.html"),
             "https://b.example": fixture_text("generic_jsonld.html")}
    results = check_all([item(u) for u in pages], fetch=pages.__getitem__)
    assert [r.price for r in results] == [Decimal("39.95"), Decimal("139.00")]
