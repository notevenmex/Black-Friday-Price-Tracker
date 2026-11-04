"""Show search results: in the terminal, or as a self-contained HTML page."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from .models import FAIR, GOOD, GREAT, HIGH, SUSPICIOUS, FindResult, MarketValue, ScoredListing

SITE_LABELS = {"ebay": "eBay", "etsy": "Etsy"}
VERDICT_TEXT = {
    GREAT: "Great deal",
    GOOD: "Good price",
    FAIR: "Fair price",
    HIGH: "Above market",
    SUSPICIOUS: "Too cheap? Check it's real",
}
BASIS_TEXT = {
    "ebay-sold": "median eBay sold price, last 90 days",
    "ebay-asking": "median eBay asking price (sold prices unavailable)",
    "manual": "your reference price",
}


def money(v: Decimal | None) -> str:
    return "?" if v is None else f"${v:,.2f}"


def pct(discount: Decimal | None) -> str:
    if discount is None:
        return ""
    if discount >= 0:
        return f"{discount * 100:.0f}% under market"
    return f"{-discount * 100:.0f}% over market"


def market_line(market: MarketValue | None) -> str:
    if market is None:
        return "Market value: unknown (too few comparable sales)"
    extra = ""
    if market.sample_size:
        extra = f", {market.sample_size} comps, {money(market.low)} to {money(market.high)}"
    return f"Market value: {money(market.price)} ({BASIS_TEXT.get(market.basis, market.basis)}{extra})"


def _price_text(s: ScoredListing) -> str:
    l = s.listing
    text = money(l.price) if l.currency == "USD" else f"{l.price} {l.currency}"
    if l.shipping:
        text += f" + {money(l.shipping)} ship"
    if l.buying_option == "auction":
        text += " (current bid" + (f", ends {l.ends_at:%b %d %H:%M} UTC" if l.ends_at else "") + ")"
    return text


def print_results(results: Sequence[FindResult], deals_only: bool = False, new_only: bool = False,
                  limit: int = 10, notes: Sequence[str] = ()) -> None:
    for r in results:
        print(f"== {r.spec.name} ==")
        print(f"   {market_line(r.market)}")
        for err in r.errors:
            print(f"   [ERROR] {err}")
        shown = [s for s in r.listings if (not deals_only or s.is_deal) and (not new_only or s.is_new)]
        if not shown:
            print("   No matching listings." if not r.listings else "   Nothing new to show.")
        for s in shown[:limit]:
            tag = "DEAL " if s.is_deal else "     "
            new = " NEW" if s.is_new and new_only is False and _any_seen(r) else ""
            site = SITE_LABELS.get(s.listing.site, s.listing.site)
            detail = ", ".join(x for x in (pct(s.discount), VERDICT_TEXT[s.verdict]) if x)
            print(f"   [{tag}] {_price_text(s)}  {site}{new}  {detail}")
            print(f"            {s.listing.title}")
            if s.listing.url:
                print(f"            {s.listing.url}")
        if len(shown) > limit:
            print(f"   ... and {len(shown) - limit} more (use --limit or --html to see all)")
        print()
    deals = sum(len(r.deals) for r in results)
    print(f"{len(results)} search(es), {deals} deal(s).")
    for note in notes:
        print(f"Note: {note}")


def _any_seen(r: FindResult) -> bool:
    """Only label NEW when some listings were seen before (i.e. not the first run)."""
    return any(not s.is_new for s in r.listings)


def write_html(results: Sequence[FindResult], path: str | Path, notes: Sequence[str] = ()) -> Path:
    path = Path(path)
    now = datetime.now(timezone.utc).astimezone().strftime("%b %d, %Y %I:%M %p")
    sections = "\n".join(_section(r) for r in results)
    note_html = "".join(f'<p class="note">{html.escape(n)}</p>' for n in notes)
    path.write_text(PAGE.format(when=html.escape(now), sections=sections, notes=note_html), encoding="utf-8")
    return path


def _section(r: FindResult) -> str:
    e = html.escape
    errs = "".join(f'<p class="err">{e(x)}</p>' for x in r.errors)
    cards = "".join(_card(s, show_new=_any_seen(r)) for s in r.listings) or \
        '<p class="muted">No matching listings.</p>'
    return (f'<section><h2>{e(r.spec.name)}</h2>'
            f'<p class="sub">{e(market_line(r.market))} · {len(r.deals)} deal(s) of {len(r.listings)}</p>'
            f'{errs}<div class="grid">{cards}</div></section>')


def _card(s: ScoredListing, show_new: bool) -> str:
    e = html.escape
    l = s.listing
    img = (f'<img src="{e(l.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">'
           if l.image_url else '<div class="noimg">No photo</div>')
    badge_cls = {GREAT: "good", GOOD: "good", SUSPICIOUS: "warning", HIGH: "bad"}.get(s.verdict, "")
    badges = f'<span class="badge {badge_cls}">{e(VERDICT_TEXT[s.verdict])}</span>'
    if show_new and s.is_new:
        badges += '<span class="badge new">New</span>'
    meta = " · ".join(x for x in (SITE_LABELS.get(l.site, l.site), l.condition, l.seller) if x)
    title = e(l.title)
    link = f'<a href="{e(l.url)}" target="_blank" rel="noopener">{title}</a>' if l.url else title
    return (f'<article class="card{" deal" if s.is_deal else ""}">{img}<div class="body">'
            f'<div class="badges">{badges}</div><div class="price">{e(_price_text(s))}</div>'
            f'<div class="disc">{e(pct(s.discount))}</div><div class="title">{link}</div>'
            f'<div class="meta">{e(meta)}</div></div></article>')


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deal Finder</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f4f3f0; --surface: #fcfcfb; --border: #e3e1dc; --grid: #ecebe7;
  --text: #0b0b0b; --text-2: #52514e; --muted: #7a7974; --link: #2a78d6;
  --good-bg: #e3f3e6; --good: #1d6b2c; --warn-bg: #fdf0d5; --warn: #7a5200;
  --bad-bg: #f9e3e3; --bad: #8a2222; --new-bg: #e3ecfa; --new: #1f4f99;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #121211; --surface: #1a1a19; --border: #2e2e2c; --grid: #262624;
    --text: #f0efec; --text-2: #c3c2b7; --muted: #8f8e87; --link: #6ea8f0;
    --good-bg: #16301c; --good: #8fd69e; --warn-bg: #33270d; --warn: #f0c46b;
    --bad-bg: #3a1a1a; --bad: #f0a0a0; --new-bg: #1a2a44; --new: #a8c6f5;
  }}
}}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px 48px; }}
h1 {{ font-size: 24px; margin: 0 0 4px; }}
h2 {{ font-size: 19px; margin: 32px 0 2px; }}
.sub, .muted, .meta {{ color: var(--muted); }}
.sub {{ margin: 0 0 12px; font-size: 13.5px; }}
.note {{ background: var(--warn-bg); color: var(--warn); padding: 8px 12px; border-radius: 8px; font-size: 13.5px; }}
.err {{ background: var(--bad-bg); color: var(--bad); padding: 8px 12px; border-radius: 8px; font-size: 13.5px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 14px; }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
  display: flex; flex-direction: column; }}
.card.deal {{ border-color: var(--good); }}
.card img, .noimg {{ width: 100%; aspect-ratio: 1; object-fit: cover; background: var(--grid); }}
.noimg {{ display: grid; place-items: center; color: var(--muted); font-size: 13px; }}
.body {{ padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 4px; }}
.badges {{ display: flex; gap: 6px; flex-wrap: wrap; }}
.badge {{ font-size: 12px; padding: 2px 8px; border-radius: 999px; background: var(--grid); color: var(--text-2); }}
.badge.good {{ background: var(--good-bg); color: var(--good); }}
.badge.warning {{ background: var(--warn-bg); color: var(--warn); }}
.badge.bad {{ background: var(--bad-bg); color: var(--bad); }}
.badge.new {{ background: var(--new-bg); color: var(--new); }}
.price {{ font-size: 18px; font-weight: 650; font-variant-numeric: tabular-nums; }}
.disc {{ font-size: 13px; color: var(--text-2); }}
.title {{ font-size: 13.5px; overflow-wrap: anywhere; }}
.meta {{ font-size: 12.5px; }}
a {{ color: var(--link); text-decoration: none; }} a:hover {{ text-decoration: underline; }}
</style></head>
<body><main>
<h1>Deal Finder</h1>
<p class="sub">Searched {when}. Prices compared to what each item actually sells for.</p>
{notes}
{sections}
</main></body></html>
"""
