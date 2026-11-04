"""One shared price table for live checks and bought/backfilled history.

Every row records where the price came from (`source`), so deal logic such
as "is today's price below the 90-day low?" works the same whether the
history came from our own scraping, Keepa, or another provider.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Iterable, Sequence

from .models import PricePoint, PriceResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    url          TEXT NOT NULL,
    name         TEXT NOT NULL,
    observed_at  TEXT NOT NULL,   -- ISO 8601, UTC
    price        TEXT,            -- decimal as text; NULL = out of stock
    currency     TEXT,
    source       TEXT NOT NULL,
    PRIMARY KEY (url, observed_at, source)
);
"""


class PriceStore:
    def __init__(self, path: str | Path):
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def add_points(self, url: str, name: str, points: Iterable[PricePoint]) -> int:
        rows = [
            (url, name, _iso(p.observed_at), None if p.price is None else str(p.price), p.currency, p.source)
            for p in points
        ]
        with self.conn:
            cur = self.conn.executemany("INSERT OR IGNORE INTO prices VALUES (?, ?, ?, ?, ?, ?)", rows)
        return cur.rowcount

    def history(self, url: str, since: datetime | None = None) -> list[PricePoint]:
        query = "SELECT observed_at, price, source, currency FROM prices WHERE url = ?"
        args: list = [url]
        if since is not None:
            query += " AND observed_at >= ?"
            args.append(_iso(since))
        rows = self.conn.execute(query + " ORDER BY observed_at", args).fetchall()
        return [
            PricePoint(datetime.fromisoformat(t), None if p is None else Decimal(p), s, c)
            for t, p, s, c in rows
        ]

    def stats(self, url: str, days: int = 90, now: datetime | None = None) -> dict[str, Decimal] | None:
        """Low / median / high over the last `days` days, or None with no data."""
        now = now or datetime.now(timezone.utc)
        prices = [p.price for p in self.history(url, since=now - timedelta(days=days)) if p.price is not None]
        if not prices:
            return None
        return {"low": min(prices), "median": Decimal(str(median(prices))), "high": max(prices)}


class PriceStoreSink:
    """Sink that records each live check in the shared price table."""

    def __init__(self, store: PriceStore):
        self.store = store

    def write(self, results: Sequence[PriceResult]) -> None:
        for r in results:
            if r.ok:
                point = PricePoint(r.checked_at, r.price, r.source or "scrape", r.currency)
                self.store.add_points(r.item.url, r.item.name, [point])


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
