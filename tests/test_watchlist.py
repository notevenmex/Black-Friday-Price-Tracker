from decimal import Decimal
from pathlib import Path

import pytest

from pricetracker.watchlist import WatchlistError, load_watchlist

ROOT = Path(__file__).parent.parent


def test_example_watchlist_loads():
    items = load_watchlist(ROOT / "watchlist.example.toml")
    assert len(items) >= 4
    assert items[0].target_price == Decimal("99.99")
    assert items[0].asin == "B0CFPJYX7P"


def test_missing_fields(tmp_path):
    path = tmp_path / "w.toml"
    path.write_text('[[item]]\nname = "x"\n')
    with pytest.raises(WatchlistError, match="url, target_price"):
        load_watchlist(path)


def test_bad_kind(tmp_path):
    path = tmp_path / "w.toml"
    path.write_text('[[item]]\nname="x"\nurl="https://a"\ntarget_price=1\nkind="other"\n')
    with pytest.raises(WatchlistError, match="unknown kind"):
        load_watchlist(path)


def test_missing_file(tmp_path):
    with pytest.raises(WatchlistError, match="not found"):
        load_watchlist(tmp_path / "nope.toml")
