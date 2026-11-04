"""Read [[search]] tables from the watchlist file."""

from __future__ import annotations

import tomllib
from decimal import Decimal
from pathlib import Path

from ..watchlist import WatchlistError
from .models import SearchSpec


def _dec(v) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _list(v) -> tuple[str, ...]:
    if v is None:
        return ()
    if isinstance(v, str):
        return tuple(x.strip() for x in v.split(",") if x.strip())
    return tuple(str(x) for x in v)


def make_spec(name: str | None = None, keywords: str = "", **opts) -> SearchSpec:
    """Build a SearchSpec from loose values (TOML or command-line flags)."""
    if not keywords.strip():
        raise WatchlistError("A search needs keywords")
    threshold = opts.get("deal_threshold")
    if threshold is not None:
        threshold = Decimal(str(threshold))
        if threshold > 1:  # "25" means 25%
            threshold /= 100
    condition = opts.get("condition")
    if condition not in (None, "new", "used"):
        raise WatchlistError(f"Unknown condition {condition!r} (use 'new' or 'used')")
    match = opts.get("match") or "all"
    if match not in ("all", "any"):
        raise WatchlistError(f"Unknown match {match!r} (use 'all' or 'any')")
    return SearchSpec(
        name=name or keywords,
        keywords=keywords,
        exclude=_list(opts.get("exclude")),
        min_price=_dec(opts.get("min_price")),
        max_price=_dec(opts.get("max_price")),
        sites=tuple(s.lower() for s in _list(opts.get("sites"))),
        condition=condition,
        deal_threshold=threshold if threshold is not None else Decimal("0.25"),
        reference_price=_dec(opts.get("reference_price")),
        match=match,
    )


def load_searches(path: str | Path) -> list[SearchSpec]:
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WatchlistError(f"Watchlist not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise WatchlistError(f"Invalid TOML in {path}: {exc}") from exc
    specs = []
    for i, entry in enumerate(data.get("search", []), start=1):
        if "keywords" not in entry:
            raise WatchlistError(f"Search #{i} is missing: keywords")
        entry = dict(entry)
        try:
            specs.append(make_spec(entry.pop("name", None), entry.pop("keywords"), **entry))
        except WatchlistError as exc:
            raise WatchlistError(f"Search #{i}: {exc}") from None
    return specs
