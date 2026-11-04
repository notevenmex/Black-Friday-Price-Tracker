# Black Friday Price Tracker

A small, reusable Python tool that watches product prices across stores and
resale sites, tells you when something drops to your target price, keeps a
price history, and draws it as charts so fake "sales" stand out.

Supported out of the box:

| Site | How prices are read | Notes |
|---|---|---|
| Amazon | product page | May return a CAPTCHA when checked too often |
| Best Buy | official Products API | Free key required: `BESTBUY_API_KEY` |
| Walmart | product page | May show a "Robot or human?" check |
| Micro Center | product page | Add `?storeid=NNN` to the URL for your store's price |
| Craigslist | search page or single posting | Terms forbid automated access; checks are spaced 5s apart |
| Facebook Marketplace | search page or single item | Terms forbid automated access; best with `FACEBOOK_COOKIE`; spaced 10s apart |
| Any other store | schema.org / Open Graph price data | Works on many shops (Newegg, B&H, Target, ...) |

Amazon price history from before you started tracking can be loaded from
[Keepa](https://keepa.com/#!api) (paid API key: `KEEPA_API_KEY`).

## Install

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Use it

```bash
cp watchlist.example.toml watchlist.toml     # then edit it
pricetracker list                            # which adapter handles each item
pricetracker check --db prices.db            # check prices and record them
pricetracker backfill --db prices.db         # optional: past Amazon prices from Keepa
pricetracker dashboard --db prices.db --open # charts in your browser
```

`check` prints one line per item:

```
[DEAL ] Kindle Paperwhite (Amazon): 94.99 (target 99.99, 5.00 under)
[wait ] Example console (Walmart): 479.00 (target 449.00)
[DEAL ] Used RTX 4080 (Craigslist SF Bay): 1 listing(s) at or under 700
          650  RTX 4080 Founders Edition (mission district)
          https://sfbay.craigslist.org/sfc/sop/d/rtx-4080/7790000001.html
[ERROR] Example TV (Best Buy, needs BESTBUY_API_KEY): Best Buy needs a free API key: ...

7 checked, 2 deal(s), 1 error(s).

At a 90-day low:
  Kindle Paperwhite (Amazon): 94.99 is at or below its 90-day low (99.99)
```

Useful flags for `check`: `--deals-only`, `--csv history.csv` (also append
to a CSV), `--delay 2` (seconds between requests). The exit code is 1 if any
item failed, so it's easy to spot problems from cron.

### Run it on a schedule

Run `check` a few times a day, not every minute: stores block aggressive
scrapers. With cron:

```cron
0 8,13,19 * * *  cd /path/to/repo && .venv/bin/pricetracker check --db prices.db --deals-only && .venv/bin/pricetracker dashboard --db prices.db
```

## The watchlist

`watchlist.toml` is a list of `[[item]]` tables. See
[`watchlist.example.toml`](watchlist.example.toml) for every option.

```toml
[[item]]
name = "Kindle Paperwhite (Amazon)"
product = "Kindle Paperwhite"   # same product at several stores = one chart
url = "https://www.amazon.com/dp/B0CFPJYX7P"
target_price = 99.99
asin = "B0CFPJYX7P"             # optional, for Keepa history

[[item]]
name = "Used RTX 4080 (Craigslist)"
url = "https://sfbay.craigslist.org/search/sss?query=rtx+4080"
target_price = 700
kind = "search"                 # report every listing at or below the target
```

## Dashboard

`pricetracker dashboard` writes one self-contained HTML file (no server, no
internet needed to view it). Each product gets a card with:

- the best current price and which store has it,
- a chart with one line per store, where bought history (Keepa) and your own
  checks share the line (dots mark your own checks),
- dashed lines for your target, the 90-day low and the 90-day median,
- a badge: "Lowest price in 90 days", "At or below your target", or a warning
  when the "deal" is no cheaper than the usual price.

Hover the chart to see every store's price on that date. It follows your
system's light or dark mode.

## Secrets

Set these as environment variables; never commit them.

| Variable | Used for |
|---|---|
| `BESTBUY_API_KEY` | Best Buy prices (free at https://developer.bestbuy.com) |
| `KEEPA_API_KEY` | Amazon price history backfill (paid) |
| `FACEBOOK_COOKIE` | Logged-in Marketplace results: the `Cookie` header from your browser on facebook.com. Using it can get that account restricted. |

## How it's built

```
src/pricetracker/
  adapters/        one file per site; picks the adapter from the URL's domain
  history/         price-history providers (Keepa) for backfilling
  sinks/           outputs: console, CSV
  store.py         SQLite price table shared by live checks and history
  dashboard.py     HTML dashboard with charts
  checker.py       runs the checks
  cli.py           the `pricetracker` command
```

**Add a store:** create `adapters/<store>.py` subclassing `SelectorAdapter`
with the store's domains and CSS selectors for the price and title (see
`adapters/microcenter.py`, it's 15 lines), add it to `ADAPTERS` in
`adapters/__init__.py`, and add a saved page under `tests/fixtures/` with a
test. If the store publishes schema.org data, the generic adapter may already
work.

**Add an output** (Google Sheets, email or push alerts): write a class with a
`write(results)` method in `sinks/` and wire it into `cli.py`.

**Add a history provider** (ShopSavvy, Wayback Machine): implement
`fetch_history(item)` returning `PricePoint`s and add it to `history/PROVIDERS`.
Every price goes into the same table with a `source` column, so the deal
checks and charts don't care where a price came from.

## Tests

```bash
pytest
```

Tests use saved pages in `tests/fixtures/` and never hit the network. Sites
change their markup; when a live check breaks, save the new page as a fixture,
fix the selectors, and add a test.

## Be a good citizen

Scraping is against the terms of several of these sites (notably Craigslist
and Facebook), and all of them block IPs that request too fast. Keep the
watchlist short, check a few times a day, and prefer official APIs (Best Buy,
Keepa) where they exist.
