"""Append each check to a CSV file to build a price history."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence

from ..models import PriceResult

FIELDS = ["checked_at", "name", "url", "price", "currency", "target_price", "is_deal", "title", "error"]


class CsvHistorySink:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def write(self, results: Sequence[PriceResult]) -> None:
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            for r in results:
                writer.writerow({
                    "checked_at": r.checked_at.isoformat(timespec="seconds"),
                    "name": r.item.name,
                    "url": r.item.url,
                    "price": "" if r.price is None else str(r.price),
                    "currency": r.currency or "",
                    "target_price": str(r.item.target_price),
                    "is_deal": r.is_deal,
                    "title": r.title or "",
                    "error": r.error or "",
                })
