"""Build a self-contained HTML dashboard from the shared price table.

    pricetracker dashboard --db prices.db -o dashboard.html

One card per product: a price chart with one line per store (bought history
and our live checks on the same line), your target price, and the 90-day
low and median so "sales" that aren't really cheaper stand out. The page is
a single file with no external dependencies; open it in any browser.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Sequence
from urllib.parse import urlparse

from .adapters import get_adapter
from .models import PricePoint, WatchItem
from .store import PriceStore

STORE_LABELS = {
    "amazon": "Amazon",
    "bestbuy": "Best Buy",
    "walmart": "Walmart",
    "microcenter": "Micro Center",
    "craigslist": "Craigslist",
    "facebook": "FB Marketplace",
}
# Fixed color slot per store, so a store keeps its color on every chart.
STORE_SLOTS = ["amazon", "bestbuy", "walmart", "microcenter", "craigslist", "facebook"]
LIVE_SOURCES = set(STORE_LABELS) | {"generic", "scrape", "craigslist", "facebook"}


def store_label(url: str) -> str:
    try:
        name = get_adapter(url).name
    except KeyError:
        name = "generic"
    if name in STORE_LABELS:
        return STORE_LABELS[name]
    return (urlparse(url).hostname or url).removeprefix("www.")


@dataclass
class StoreSeries:
    store: str
    url: str
    target: Decimal
    points: list[PricePoint]
    slot: int = 0

    @property
    def current(self) -> PricePoint | None:
        priced = [p for p in self.points if p.price is not None]
        return priced[-1] if priced else None


@dataclass
class ProductCard:
    name: str
    target: Decimal
    series: list[StoreSeries]
    low90: Decimal | None = None
    median90: Decimal | None = None
    best: StoreSeries | None = None
    verdicts: list[tuple[str, str]] = field(default_factory=list)  # (kind, text)


def build_cards(items: Sequence[WatchItem], store: PriceStore, now: datetime | None = None,
                days: int = 90) -> list[ProductCard]:
    now = now or datetime.now(timezone.utc)
    groups: dict[str, list[WatchItem]] = {}
    for item in items:
        # Search watches chart their lowest listing price over time.
        groups.setdefault(item.group, []).append(item)

    cards = []
    for name, group in groups.items():
        series = []
        for item in group:
            label = store_label(item.url)
            series.append(StoreSeries(label, item.url, item.target_price, store.history(item.url)))
        next_free = len(STORE_SLOTS)
        for s in series:
            key = next((k for k, v in STORE_LABELS.items() if v == s.store), None)
            if key in STORE_SLOTS:
                s.slot = STORE_SLOTS.index(key)
            else:
                s.slot, next_free = min(next_free, 7), next_free + 1

        card = ProductCard(name=name, target=min(i.target_price for i in group), series=series)
        recent = [p.price for s in series for p in s.points
                  if p.price is not None and p.observed_at >= now - timedelta(days=days)]
        if recent:
            card.low90 = min(recent)
            card.median90 = Decimal(str(median(recent)))
        current = [s for s in series if s.current]
        if current:
            card.best = min(current, key=lambda s: s.current.price)
        card.verdicts = verdicts(card)
        cards.append(card)
    return cards


def verdicts(card: ProductCard) -> list[tuple[str, str]]:
    if card.best is None:
        return [("muted", "No prices yet")]
    price = card.best.current.price
    out = []
    if price <= card.target:
        out.append(("good", f"At or below your target of ${card.target}"))
    if card.low90 is not None and price <= card.low90:
        out.append(("good", "Lowest price in 90 days"))
    elif card.median90 is not None and price >= card.median90:
        out.append(("warning", "Not cheaper than its usual (90-day median) price"))
    if not out:
        out.append(("muted", "Below its usual price, above your target"))
    return out


def _payload(cards: list[ProductCard]) -> list[dict]:
    data = []
    for c in cards:
        data.append({
            "name": c.name,
            "target": float(c.target),
            "low90": None if c.low90 is None else float(c.low90),
            "median90": None if c.median90 is None else float(c.median90),
            "series": [
                {
                    "store": s.store,
                    "slot": s.slot,
                    "points": [
                        [int(p.observed_at.timestamp() * 1000),
                         None if p.price is None else float(p.price),
                         p.source in LIVE_SOURCES]
                        for p in s.points
                    ],
                }
                for s in c.series
            ],
        })
    return data


def render(cards: list[ProductCard], generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    esc = html.escape
    card_html = []
    for i, c in enumerate(cards):
        rows = []
        for s in sorted(c.series, key=lambda s: (s.current is None, s.current.price if s.current else 0)):
            cur = s.current
            price = f"${cur.price:,.2f}" if cur else "—"
            when = cur.observed_at.strftime("%b %d") if cur else ""
            rows.append(
                f'<tr><td><span class="sw s{s.slot}"></span>{esc(s.store)}</td>'
                f'<td class="num">{price}</td><td class="muted">{when}</td>'
                f'<td><a href="{esc(s.url)}" target="_blank" rel="noopener">open</a></td></tr>'
            )
        badges = "".join(f'<span class="badge {k}">{esc(t)}</span>' for k, t in c.verdicts)
        best = (f'<div class="hero">${c.best.current.price:,.2f}</div>'
                f'<div class="muted">best price, at {esc(c.best.store)}</div>') if c.best else ""
        stats = []
        if c.low90 is not None:
            stats.append(f"90-day low <b>${c.low90:,.2f}</b>")
            stats.append(f"median <b>${c.median90:,.2f}</b>")
        stats.append(f"target <b>${c.target:,.2f}</b>")
        card_html.append(f"""
<section class="card">
  <header>
    <div><h2>{esc(c.name)}</h2><div class="badges">{badges}</div></div>
    <div class="right">{best}</div>
  </header>
  <div class="stats muted">{" · ".join(stats)}</div>
  <div class="chart" data-index="{i}"></div>
  <table><thead><tr><th>Store</th><th class="num">Latest</th><th>Seen</th><th></th></tr></thead>
  <tbody>{"".join(rows)}</tbody></table>
</section>""")

    body = "".join(card_html) or '<p class="muted">No products in the watchlist yet.</p>'
    data = json.dumps(_payload(cards)).replace("</", "<\\/")
    return (TEMPLATE
            .replace("{{GENERATED}}", generated_at.strftime("%Y-%m-%d %H:%M UTC"))
            .replace("{{CARDS}}", body)
            .replace("{{DATA}}", data))


def write_dashboard(items: Sequence[WatchItem], store: PriceStore, out: str | Path) -> Path:
    out = Path(out)
    out.write_text(render(build_cards(items, store)), encoding="utf-8")
    return out


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Price Tracker</title>
<style>
:root {
  color-scheme: light;
  --bg: #f4f3f0; --surface: #fcfcfb; --border: #e3e1dc;
  --text: #0b0b0b; --text-2: #52514e; --muted: #7a7974; --grid: #ecebe7;
  --s0: #2a78d6; --s1: #eb6834; --s2: #1baf7a; --s3: #eda100;
  --s4: #e87ba4; --s5: #008300; --s6: #6250d6; --s7: #e34948;
  --good-bg: #e3f3e6; --good: #1d6b2c; --warn-bg: #fdf0d5; --warn: #7a5200;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #121211; --surface: #1a1a19; --border: #2e2e2c;
    --text: #f0efec; --text-2: #c3c2b7; --muted: #8f8e87; --grid: #262624;
    --s0: #3987e5; --s1: #d95926; --s2: #199e70; --s3: #c98500;
    --s4: #d55181; --s5: #008300; --s6: #9085e9; --s7: #e66767;
    --good-bg: #16301c; --good: #8fd69e; --warn-bg: #33270d; --warn: #f0c46b;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #121211; --surface: #1a1a19; --border: #2e2e2c;
  --text: #f0efec; --text-2: #c3c2b7; --muted: #8f8e87; --grid: #262624;
  --s0: #3987e5; --s1: #d95926; --s2: #199e70; --s3: #c98500;
  --s4: #d55181; --s5: #008300; --s6: #9085e9; --s7: #e66767;
  --good-bg: #16301c; --good: #8fd69e; --warn-bg: #33270d; --warn: #f0c46b;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 960px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 0 0 6px; }
.muted { color: var(--muted); }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 18px; margin-top: 18px; }
.card header { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.right { text-align: right; }
.hero { font-size: 28px; font-weight: 650; font-variant-numeric: tabular-nums; }
.badges { display: flex; gap: 6px; flex-wrap: wrap; }
.badge { font-size: 12.5px; padding: 2px 8px; border-radius: 999px; background: var(--grid); color: var(--text-2); }
.badge.good { background: var(--good-bg); color: var(--good); }
.badge.good::before { content: "✓ "; }
.badge.warning { background: var(--warn-bg); color: var(--warn); }
.badge.warning::before { content: "! "; }
.stats { font-size: 13.5px; margin: 8px 0 4px; }
.stats b { color: var(--text-2); font-weight: 600; font-variant-numeric: tabular-nums; }
.chart { position: relative; margin: 8px 0; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.chart .empty { padding: 32px 0; text-align: center; }
.legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 13px; color: var(--text-2); margin-bottom: 4px; }
.sw { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
.s0 { background: var(--s0); } .s1 { background: var(--s1); } .s2 { background: var(--s2); } .s3 { background: var(--s3); }
.s4 { background: var(--s4); } .s5 { background: var(--s5); } .s6 { background: var(--s6); } .s7 { background: var(--s7); }
.tip { position: absolute; pointer-events: none; background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 6px 9px; font-size: 13px; box-shadow: 0 4px 14px rgba(0,0,0,.12);
  white-space: nowrap; display: none; z-index: 2; }
.tip .row { display: flex; gap: 10px; justify-content: space-between; font-variant-numeric: tabular-nums; }
table { width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 6px; }
th { text-align: left; font-weight: 500; color: var(--muted); font-size: 12.5px; border-bottom: 1px solid var(--border); padding: 4px 6px; }
td { padding: 6px; border-bottom: 1px solid var(--grid); }
.num { text-align: right; font-variant-numeric: tabular-nums; }
a { color: var(--s0); }
</style></head>
<body><main>
<h1>Black Friday price tracker</h1>
<div class="muted">Generated {{GENERATED}}. Solid dots are our own checks; lines include bought history.</div>
{{CARDS}}
</main>
<script id="data" type="application/json">{{DATA}}</script>
<script>
(function () {
  const DATA = JSON.parse(document.getElementById("data").textContent);
  const NS = "http://www.w3.org/2000/svg";
  const W = 880, H = 260, M = { l: 52, r: 96, t: 12, b: 26 };
  const fmt = v => "$" + v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const day = t => new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "2-digit" });

  function el(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function niceTicks(lo, hi, n) {
    const span = hi - lo || 1, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= step0);
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(v);
    return out;
  }
  // Price at time t: prices hold until the next change (step line).
  function priceAt(points, t) {
    let v = null;
    for (const p of points) { if (p[0] > t) break; v = p[1]; }
    return v;
  }

  document.querySelectorAll(".chart").forEach(box => {
    const c = DATA[+box.dataset.index];
    const all = c.series.flatMap(s => s.points);
    const priced = all.filter(p => p[1] !== null);
    if (!priced.length) { box.innerHTML = '<div class="empty muted">No price data yet. Run <code>pricetracker check --db</code> or <code>backfill</code>.</div>'; return; }

    if (c.series.length > 1) {
      const lg = document.createElement("div"); lg.className = "legend";
      c.series.forEach(s => { const i = document.createElement("span");
        i.innerHTML = '<span class="sw s' + s.slot + '"></span>'; i.append(s.store); lg.appendChild(i); });
      box.appendChild(lg);
    }

    const now = Date.now();
    let x0 = Math.min(...all.map(p => p[0])), x1 = Math.max(now, ...all.map(p => p[0]));
    if (x1 - x0 < 864e5) x0 = x1 - 864e5 * 7;
    const refs = [c.target, c.low90, c.median90].filter(v => v !== null);
    let y0 = Math.min(...priced.map(p => p[1]), ...refs), y1 = Math.max(...priced.map(p => p[1]), ...refs);
    const pad = (y1 - y0 || y1 * 0.1 || 1) * 0.12; y0 = Math.max(0, y0 - pad); y1 += pad;
    const X = t => M.l + (t - x0) / (x1 - x0) * (W - M.l - M.r);
    const Y = v => M.t + (1 - (v - y0) / (y1 - y0)) * (H - M.t - M.b);

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Price history for " + c.name }, box);
    const ticks = niceTicks(y0, y1, 4);
    ticks.forEach(v => {
      el("line", { x1: M.l, x2: W - M.r, y1: Y(v), y2: Y(v), stroke: "var(--grid)" }, svg);
      el("text", { x: M.l - 8, y: Y(v) + 4, "text-anchor": "end", "font-size": 11.5, fill: "var(--muted)" }, svg).textContent = "$" + v.toLocaleString();
    });
    [0, 0.5, 1].forEach(f => {
      const t = x0 + f * (x1 - x0);
      el("text", { x: X(t), y: H - 6, "text-anchor": f === 0 ? "start" : f === 1 ? "end" : "middle", "font-size": 11.5, fill: "var(--muted)" }, svg).textContent = day(t);
    });

    // Reference lines, labeled at the right edge in text ink.
    const refLines = [["target", c.target, "4 4"], ["90d low", c.low90, "1 3"], ["median", c.median90, "1 3"]]
      .filter(r => r[1] !== null);
    let lastY = -99;
    refLines.sort((a, b) => b[1] - a[1]).forEach(([label, v, dash]) => {
      el("line", { x1: M.l, x2: W - M.r, y1: Y(v), y2: Y(v), stroke: "var(--text-2)", "stroke-width": 1, "stroke-dasharray": dash, opacity: 0.8 }, svg);
      let ly = Math.max(Y(v) + 4, lastY + 13); lastY = ly;
      el("text", { x: W - M.r + 6, y: ly, "font-size": 11.5, fill: "var(--text-2)" }, svg).textContent = label + " " + fmt(v);
    });

    c.series.forEach(s => {
      const color = `var(--s${s.slot})`;
      let d = "", prev = null;
      s.points.forEach(p => {
        if (p[1] === null) { prev = null; return; }
        const x = X(p[0]), y = Y(p[1]);
        d += prev ? `H${x}V${y}` : `M${x},${y}`;
        prev = p;
      });
      const last = s.points.filter(p => p[1] !== null).slice(-1)[0];
      if (last) d += `H${X(Math.max(now, last[0]))}`;
      el("path", { d, fill: "none", stroke: color, "stroke-width": 2, "stroke-linejoin": "round" }, svg);
      s.points.filter(p => p[2] && p[1] !== null).forEach(p =>
        el("circle", { cx: X(p[0]), cy: Y(p[1]), r: 4, fill: color, stroke: "var(--surface)", "stroke-width": 2 }, svg));
    });

    // Hover: crosshair + tooltip with every store's price at that date.
    const cross = el("line", { y1: M.t, y2: H - M.b, stroke: "var(--muted)", "stroke-width": 1, visibility: "hidden" }, svg);
    const tip = document.createElement("div"); tip.className = "tip"; box.appendChild(tip);
    const hit = el("rect", { x: M.l, y: M.t, width: W - M.l - M.r, height: H - M.t - M.b, fill: "transparent" }, svg);
    function move(evt) {
      const r = svg.getBoundingClientRect(), sx = (evt.clientX - r.left) * W / r.width;
      const t = x0 + (Math.min(Math.max(sx, M.l), W - M.r) - M.l) / (W - M.l - M.r) * (x1 - x0);
      cross.setAttribute("x1", X(t)); cross.setAttribute("x2", X(t)); cross.setAttribute("visibility", "visible");
      const rows = c.series.map(s => [s, priceAt(s.points, t)]).filter(r => r[1] !== null)
        .sort((a, b) => a[1] - b[1]);
      tip.innerHTML = "<div class='muted'>" + day(t) + "</div>" + (rows.length ? rows.map(([s, v]) =>
        `<div class="row"><span><span class="sw s${s.slot}"></span>${s.store.replace(/</g, "&lt;")}</span><b>${fmt(v)}</b></div>`).join("")
        : "<div class='muted'>no price</div>");
      tip.style.display = "block";
      const px = (X(t) / W) * r.width;
      tip.style.left = Math.min(px + 12, r.width - tip.offsetWidth) + "px";
      tip.style.top = "8px";
    }
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerleave", () => { tip.style.display = "none"; cross.setAttribute("visibility", "hidden"); });
  });
})();
</script>
</body></html>
"""
