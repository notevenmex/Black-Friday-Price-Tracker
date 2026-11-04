"""Track product prices against target prices for Black Friday deals."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .adapters import get_adapter
from .checker import check_all
from .dashboard import write_dashboard
from .history import PROVIDERS, HistoryError
from .sinks import ConsoleSink, CsvHistorySink, Sink
from .store import PriceStore, PriceStoreSink
from .watchlist import WatchlistError, load_watchlist


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pricetracker", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-w", "--watchlist", default="watchlist.toml",
                        help="path to the watchlist TOML file (default: watchlist.toml)")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="fetch current prices and compare to targets")
    check.add_argument("--db", metavar="PATH", help="record prices in this SQLite price table "
                       "and compare against its 90-day low")
    check.add_argument("--csv", metavar="PATH", help="append results to this CSV file")
    check.add_argument("--deals-only", action="store_true", help="only print items at or below target")
    check.add_argument("--delay", type=float, default=2.0,
                       help="seconds to wait between requests (default: 2)")

    backfill = sub.add_parser("backfill", help="load past prices from history providers (e.g. Keepa)")
    backfill.add_argument("--db", metavar="PATH", required=True, help="SQLite price table to fill")

    dash = sub.add_parser("dashboard", help="write an HTML dashboard with price charts")
    dash.add_argument("--db", metavar="PATH", required=True, help="SQLite price table to read")
    dash.add_argument("-o", "--output", default="dashboard.html", help="output file (default: dashboard.html)")
    dash.add_argument("--open", action="store_true", help="open the dashboard in your browser")

    sub.add_parser("list", help="show the watchlist and which adapter each item uses")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        items = load_watchlist(args.watchlist)
    except WatchlistError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "list":
        for item in items:
            try:
                adapter = get_adapter(item.url, item.adapter).name
            except KeyError as exc:
                adapter = f"?? {exc}"
            print(f"{item.name}  [{item.kind}]  target={item.target_price}  adapter={adapter}\n  {item.url}")
        return 0

    if args.command == "backfill":
        return _backfill(items, args.db)

    if args.command == "dashboard":
        store = PriceStore(args.db)
        out = write_dashboard(items, store, args.output)
        store.close()
        print(f"Wrote {out}")
        if args.open:
            import webbrowser

            webbrowser.open(out.resolve().as_uri())
        return 0

    results = check_all(items, delay=args.delay)
    sinks: list[Sink] = [ConsoleSink(deals_only=args.deals_only)]
    if args.csv:
        sinks.append(CsvHistorySink(args.csv))
    store = PriceStore(args.db) if args.db else None
    before = {}
    if store:
        # Snapshot past stats before today's prices are recorded.
        before = {r.item.url: store.stats(r.item.url, days=90) for r in results}
        sinks.append(PriceStoreSink(store))
    for sink in sinks:
        sink.write(results)

    if store:
        _print_vs_history(results, before)
        store.close()

    # Exit 0 when everything was checked; 1 if any check failed.
    return 1 if any(not r.ok for r in results) else 0


def _backfill(items, db_path: str) -> int:
    store = PriceStore(db_path)
    failures = 0
    for item in items:
        provider = next((p for p in PROVIDERS if p.supports(item)), None)
        if provider is None:
            print(f"[skip ] {item.name}: no history provider for this item")
            continue
        try:
            points = provider.fetch_history(item)
        except HistoryError as exc:
            failures += 1
            print(f"[ERROR] {item.name}: {exc}")
            continue
        added = store.add_points(item.url, item.name, points)
        print(f"[ok   ] {item.name}: {added} new price points from {provider.name}")
    store.close()
    return 1 if failures else 0


def _print_vs_history(results, before: dict) -> None:
    lines = []
    for r in results:
        if not r.ok or r.item.kind != "product":
            continue
        stats = before.get(r.item.url)
        if stats and r.price <= stats["low"]:
            lines.append(f"  {r.item.name}: {r.price} is at or below its 90-day low ({stats['low']})")
    if lines:
        print("\nAt a 90-day low:")
        print("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
