"""Remember listings already shown, so repeat runs can show only new ones.

Lives in the same SQLite file as the price table (`--db prices.db`). The
market value of each search is also stored in the shared `prices` table
under the URL `search:<name>`, so it builds a history like any other price.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from ..models import PricePoint
from ..store import PriceStore
from .models import MarketValue, ScoredListing, SearchSpec

SCHEMA = """
CREATE TABLE IF NOT EXISTS found_listings (
    search      TEXT NOT NULL,
    site        TEXT NOT NULL,
    listing_id  TEXT NOT NULL,
    title       TEXT,
    url         TEXT,
    first_price TEXT,
    last_price  TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    PRIMARY KEY (search, site, listing_id)
);
"""


class SeenStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)
        self.prices = PriceStore(self.path)

    def close(self) -> None:
        self.conn.close()
        self.prices.close()

    def mark(self, spec: SearchSpec, scored: Sequence[ScoredListing]) -> list[ScoredListing]:
        """Return the listings with `is_new` set, and remember them."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        out = []
        with self.conn:
            for s in scored:
                l = s.listing
                row = self.conn.execute(
                    "SELECT 1 FROM found_listings WHERE search=? AND site=? AND listing_id=?",
                    (spec.name, l.site, l.listing_id)).fetchone()
                if row:
                    self.conn.execute(
                        "UPDATE found_listings SET last_price=?, last_seen=? "
                        "WHERE search=? AND site=? AND listing_id=?",
                        (str(l.total), now, spec.name, l.site, l.listing_id))
                else:
                    self.conn.execute("INSERT INTO found_listings VALUES (?,?,?,?,?,?,?,?,?)",
                                      (spec.name, l.site, l.listing_id, l.title, l.url,
                                       str(l.total), str(l.total), now, now))
                out.append(replace(s, is_new=row is None))
        return out

    def record_market(self, spec: SearchSpec, market: MarketValue) -> None:
        point = PricePoint(datetime.now(timezone.utc), market.price, market.basis, "USD")
        self.prices.add_points(f"search:{spec.name}", spec.name, [point])
