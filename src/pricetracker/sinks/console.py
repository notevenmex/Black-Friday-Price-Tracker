"""Print results as a readable table."""

from __future__ import annotations

import sys
from typing import Sequence, TextIO

from ..models import PriceResult


class ConsoleSink:
    def __init__(self, stream: TextIO | None = None, deals_only: bool = False, max_listings: int = 10):
        self.stream = stream or sys.stdout
        self.deals_only = deals_only
        self.max_listings = max_listings

    def write(self, results: Sequence[PriceResult]) -> None:
        shown = [r for r in results if r.is_deal] if self.deals_only else list(results)
        if not shown:
            print("No deals at or below target right now." if self.deals_only else "Nothing to show.",
                  file=self.stream)
            return
        for r in shown:
            if not r.ok:
                status, detail = "ERROR", r.error
            elif r.is_deal and r.item.kind == "search":
                status = "DEAL "
                detail = f"{len(r.deal_listings)} listing(s) at or under {r.item.target_price}"
            elif r.is_deal:
                status, detail = "DEAL ", f"{r.price} (target {r.item.target_price}, {r.savings} under)"
            else:
                status, detail = "wait ", f"{r.price} (target {r.item.target_price})"
            print(f"[{status}] {r.item.name}: {detail}", file=self.stream)
            for listing in r.deal_listings[: self.max_listings]:
                where = f" ({listing.location})" if listing.location else ""
                print(f"          {listing.price}  {listing.title}{where}\n"
                      f"          {listing.url or ''}", file=self.stream)
        deals = sum(r.is_deal for r in results)
        errors = sum(not r.ok for r in results)
        print(f"\n{len(results)} checked, {deals} deal(s), {errors} error(s).", file=self.stream)
