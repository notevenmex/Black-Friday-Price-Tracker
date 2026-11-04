from datetime import datetime, timedelta, timezone
from decimal import Decimal

from pricetracker import cli
from pricetracker.dashboard import build_cards, render
from pricetracker.models import PricePoint, WatchItem
from pricetracker.store import PriceStore

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)
AMZ = "https://www.amazon.com/dp/B0CL61F39H"
WMT = "https://www.walmart.com/ip/5113183757"


def pt(days_ago, price, source):
    return PricePoint(NOW - timedelta(days=days_ago), Decimal(price), source)


def make(tmp_path, amazon_now="429.99"):
    store = PriceStore(tmp_path / "p.db")
    store.add_points(AMZ, "PS5", [pt(60, "479.99", "keepa"), pt(30, "459.99", "keepa"), pt(0, amazon_now, "amazon")])
    store.add_points(WMT, "PS5", [pt(1, "449.00", "walmart")])
    items = [WatchItem("PS5 (Amazon)", AMZ, Decimal("399"), product="PS5"),
             WatchItem("PS5 (Walmart)", WMT, Decimal("399"), product="PS5"),
             WatchItem("No data", "https://shop.example/x", Decimal("10"))]
    return items, store


def test_products_group_stores_on_one_card(tmp_path):
    items, store = make(tmp_path)
    cards = build_cards(items, store, now=NOW)
    assert [c.name for c in cards] == ["PS5", "No data"]
    ps5 = cards[0]
    assert {s.store for s in ps5.series} == {"Amazon", "Walmart"}
    assert ps5.best.store == "Amazon" and ps5.best.current.price == Decimal("429.99")
    assert ps5.low90 == Decimal("429.99")
    assert ("good", "Lowest price in 90 days") in ps5.verdicts
    assert cards[1].verdicts == [("muted", "No prices yet")]


def test_store_colors_are_fixed(tmp_path):
    items, store = make(tmp_path)
    slots = {s.store: s.slot for s in build_cards(items, store, now=NOW)[0].series}
    assert slots == {"Amazon": 0, "Walmart": 2}


def test_fake_sale_is_flagged(tmp_path):
    items, store = make(tmp_path, amazon_now="499.99")
    store.add_points(WMT, "PS5", [pt(0, "499.00", "walmart")])
    ps5 = build_cards(items, store, now=NOW)[0]
    assert any(kind == "warning" for kind, _ in ps5.verdicts)


def test_search_watch_gets_a_chart(tmp_path):
    store = PriceStore(tmp_path / "p.db")
    url = "https://sfbay.craigslist.org/search/sss?query=4080"
    store.add_points(url, "4080", [pt(1, "650", "craigslist")])
    [card] = build_cards([WatchItem("Used 4080", url, Decimal("700"), kind="search")], store, now=NOW)
    assert card.series[0].store == "Craigslist" and card.best.current.price == Decimal("650")


def test_render_is_self_contained_and_escaped(tmp_path):
    store = PriceStore(tmp_path / "p.db")
    items = [WatchItem("<script>alert(1)</script>", "https://shop.example/x", Decimal("10"))]
    page = render(build_cards(items, store, now=NOW), generated_at=NOW)
    assert "<script>alert(1)</script>" not in page
    assert "src=\"http" not in page and "<link" not in page


def test_cli_dashboard(tmp_path, capsys):
    wl = tmp_path / "w.toml"
    wl.write_text('[[item]]\nname="Mouse"\nurl="https://shop.example/m"\ntarget_price=40\n')
    out = tmp_path / "d.html"
    assert cli.main(["-w", str(wl), "dashboard", "--db", str(tmp_path / "p.db"), "-o", str(out)]) == 0
    assert "Mouse" in out.read_text()
