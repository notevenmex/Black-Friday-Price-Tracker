"""Load the watchlist file."""

from __future__ import annotations

import tomllib
from decimal import Decimal
from pathlib import Path

from .models import PRODUCT, SEARCH, WatchItem


class WatchlistError(ValueError):
    pass


def load_watchlist(path: str | Path) -> list[WatchItem]:
    """Read a TOML watchlist made of [[item]] tables."""
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WatchlistError(f"Watchlist not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise WatchlistError(f"Invalid TOML in {path}: {exc}") from exc

    items = []
    for i, entry in enumerate(data.get("item", []), start=1):
        missing = [k for k in ("name", "url", "target_price") if k not in entry]
        if missing:
            raise WatchlistError(f"Item #{i} is missing: {', '.join(missing)}")
        kind = entry.get("kind", PRODUCT)
        if kind not in (PRODUCT, SEARCH):
            raise WatchlistError(f"Item #{i} has unknown kind {kind!r} (use 'product' or 'search')")
        items.append(
            WatchItem(
                name=str(entry["name"]),
                url=str(entry["url"]),
                target_price=Decimal(str(entry["target_price"])),
                adapter=entry.get("adapter"),
                kind=kind,
                product=entry.get("product"),
                asin=entry.get("asin"),
                upc=str(entry["upc"]) if "upc" in entry else None,
            )
        )
    return items
