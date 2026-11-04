import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from pricetracker.history.base import HistoryError
from pricetracker.history.keepa import KeepaHistory, asin_for, keepa_time
from pricetracker.models import PricePoint, PriceResult, WatchItem
from pricetracker.store import PriceStore, PriceStoreSink

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)
URL = "https://www.amazon.com/dp/B0CFPJYX7P"


def point(days_ago, price, source="keepa"):
    return PricePoint(NOW - timedelta(days=days_ago), None if price is None else Decimal(price), source)


def test_store_stats_mix_sources(tmp_path):
    store = PriceStore(tmp_path / "p.db")
    store.add_points(URL, "Kindle", [point(200, "79.99"), point(60, "129.99"), point(30, None)])
    store.add_points(URL, "Kindle", [point(1, "109.99", source="amazon")])
    stats = store.stats(URL, days=90, now=NOW)
    # The 200-day-old $79.99 and the out-of-stock point are excluded.
    assert stats == {"low": Decimal("109.99"), "median": Decimal("119.99"), "high": Decimal("129.99")}
    assert {p.source for p in store.history(URL)} == {"keepa", "amazon"}


def test_store_ignores_duplicates(tmp_path):
    store = PriceStore(tmp_path / "p.db")
    assert store.add_points(URL, "K", [point(1, "10")]) == 1
    assert store.add_points(URL, "K", [point(1, "10")]) == 0


def test_store_sink_records_live_checks(tmp_path):
    store = PriceStore(tmp_path / "p.db")
    item = WatchItem("Kindle", URL, Decimal("100"))
    PriceStoreSink(store).write([
        PriceResult(item, Decimal("95"), "USD", source="amazon"),
        PriceResult(item, None, error="blocked"),
    ])
    [p] = store.history(URL)
    assert p.price == Decimal("95") and p.source == "amazon"


def test_keepa_time():
    assert keepa_time(0) == datetime(2011, 1, 1, tzinfo=timezone.utc)


def test_asin_from_url_or_field():
    assert asin_for(WatchItem("x", URL, Decimal(1))) == "B0CFPJYX7P"
    assert asin_for(WatchItem("x", "https://a.example", Decimal(1), asin="B000000000")) == "B000000000"
    assert asin_for(WatchItem("x", "https://a.example", Decimal(1))) is None


def test_keepa_parses_history(fixture_text):
    calls = []

    def fake_get(url, params):
        calls.append(params)
        return json.loads(fixture_text("keepa_product.json"))

    provider = KeepaHistory(api_key="k", get_json=fake_get)
    points = provider.fetch_history(WatchItem("Kindle", URL, Decimal("100")))
    assert calls[0]["asin"] == "B0CFPJYX7P" and calls[0]["domain"] == 1
    assert [p.price for p in points] == [Decimal("149.99"), Decimal("129.99"), None]
    assert {p.source for p in points} == {"keepa"}


def test_keepa_falls_back_to_new_offers():
    payload = {"products": [{"csv": [[7000000, -1], [7000000, 13999]]}]}
    points = KeepaHistory(api_key="k", get_json=lambda u, p: payload).fetch_history(
        WatchItem("Kindle", URL, Decimal("100")))
    assert [p.price for p in points] == [Decimal("139.99")]


def test_keepa_needs_key(monkeypatch):
    monkeypatch.delenv("KEEPA_API_KEY", raising=False)
    with pytest.raises(HistoryError, match="KEEPA_API_KEY"):
        KeepaHistory().fetch_history(WatchItem("x", URL, Decimal(1)))
