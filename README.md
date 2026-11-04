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

## Find deals on unique items

Some things have no product page to watch: artist and tour jerseys, limited
drops, vintage pieces. `pricetracker find` searches marketplaces by keyword
and compares every listing with what that item actually **sold** for on
eBay, so you can tell a real bargain from a normal asking price.

```bash
pricetracker find "travis scott jersey" --exclude replica,kids --max-price 120
pricetracker find                                # every [[search]] in watchlist.toml
pricetracker find --db prices.db --new-only      # only listings you haven't seen yet
pricetracker find --html finds.html --open       # a page with photos
```

```
== Travis Scott Cactus Jack jersey ==
   Market value: $145.00 (median eBay sold price, last 90 days, 4 comps, $130.00 to $165.00)
   [DEAL ] $85.00  Etsy  41% under market, Great deal
            Travis Scott Cactus Jack Jersey "Astroworld" vintage style
            https://www.etsy.com/listing/3001/travis-scott-jersey
   [DEAL ] $95.00 + $5.00 ship  eBay  31% under market, Great deal
            Travis Scott Cactus Jack Houston Astros Jersey Size L
            https://www.ebay.com/itm/1001
   [     ] $180.00  eBay  24% over market, Above market
            Travis Scott Astros Jersey Cactus Jack NWT XL
            https://www.ebay.com/itm/1002
```

Sites (official APIs only, no scraping):

| Site | API | Keys |
|---|---|---|
| eBay | Browse API for live listings | `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`: a free production keyset from https://developer.ebay.com/my/keys |
| eBay sold prices | Marketplace Insights API | Same keys, but eBay must approve your app for this API. Until then, market value is the median **asking** price of live Buy It Now listings, which runs higher than sale prices, so fewer things look like deals |
| Etsy | Open API v3 | `ETSY_API_KEY` (and `ETSY_SHARED_SECRET` if Etsy asks for `keystring:secret`), free from https://www.etsy.com/developers/your-apps. Shipping isn't in Etsy's search results, so Etsy totals exclude it |

How a listing is judged:

- Its title must contain every keyword (`match = "any"` relaxes this) and
  none of the `exclude` words. Marketplace search is loose, and excludes
  such as `replica`, `custom` or `kids` filter out most of the noise.
- **Market value** is the median eBay sold price over 90 days, from titles
  that pass the same keyword filter, ignoring outliers such as bulk lots.
  Set `reference_price` if you know the going rate better.
- Total price (item + shipping) at least `deal_threshold` (default 25%)
  under market value is a **Great deal**, 10% under is a **Good price**.
  Anything at or under your `max_price` is always flagged.
- More than 60% under market is labelled **Too cheap? Check it's real**:
  for jerseys that usually means a fake, a kids' size or a scam. Auctions
  show the current bid and its end time; the final price will be higher.

With `--db`, listings are remembered so `--new-only` shows only new ones,
and each search's market value is saved to the price table under
`search:<name>` so it builds up a history.

## Use it from Claude

The tracker comes with an MCP server, so you can run it by chatting with
Claude in the **Claude desktop app** or **Claude Code**, with no commands to
remember:

> Find Travis Scott Cactus Jack jerseys under $120, no replicas or kids sizes.
>
> Save that as a search, and also watch a Bad Bunny jersey.
>
> Add https://www.target.com/p/... to my watchlist with a target of $399.
>
> Check my prices. Has the PS5 been cheaper than this in the last 90 days?
>
> Show me the dashboard.

Claude picks the right tool, runs it on your computer and replies with the
listings (links, price vs. market value, fake warnings). The tools:

| Tool | What it does |
|---|---|
| `find_deals` | Keyword search on eBay and Etsy, scored against eBay sold prices; can open a results page with photos |
| `add_saved_search` / `run_saved_searches` | Save keyword searches and re-run them, optionally showing only new listings |
| `add_watch_item` / `check_prices` | Watch product pages with a target price and check them |
| `show_watchlist` | What you're watching |
| `price_history` | How a product's price, or a search's market value, has moved |
| `build_dashboard` | Open the chart dashboard in your browser |

Your files go in `~/.pricetracker/` (`watchlist.toml`, `prices.db`, the HTML
pages). Set `PRICETRACKER_HOME` to use another folder, or
`PRICETRACKER_WATCHLIST` / `PRICETRACKER_DB` to point at existing files.

### Set it up

1. Install with the Claude extra (inside the repository's virtual environment):

   ```bash
   pip install -e ".[claude]"
   which pricetracker-mcp      # Windows: where pricetracker-mcp
   ```

   Note the full path it prints; you need it below.

2. **Claude desktop app:** open Settings, then Developer, then Edit Config,
   and add the server to `claude_desktop_config.json` (use your own path and
   keys), then restart the app:

   ```json
   {
     "mcpServers": {
       "pricetracker": {
         "command": "/Users/you/Black-Friday-Price-Tracker/.venv/bin/pricetracker-mcp",
         "env": {
           "EBAY_CLIENT_ID": "your-ebay-app-id",
           "EBAY_CLIENT_SECRET": "your-ebay-cert-id",
           "ETSY_API_KEY": "optional",
           "BESTBUY_API_KEY": "optional"
         }
       }
     }
   }
   ```

   On Windows, write the path with doubled backslashes, like
   `C:\\Users\\you\\Black-Friday-Price-Tracker\\.venv\\Scripts\\pricetracker-mcp.exe`.

3. **Claude Code:** the repository's `.mcp.json` registers the server when
   you start `claude` in this folder with the virtual environment active
   (approve it when asked). To have it in every folder instead:

   ```bash
   claude mcp add pricetracker --scope user \
     -e EBAY_CLIENT_ID=... -e EBAY_CLIENT_SECRET=... \
     -- /full/path/to/.venv/bin/pricetracker-mcp
   ```

The server runs on your computer, so it works in the desktop app and
Claude Code but not on claude.ai in a browser or on your phone.

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
| `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` | eBay search and sold prices for `find` (free at https://developer.ebay.com/my/keys) |
| `ETSY_API_KEY`, `ETSY_SHARED_SECRET` | Etsy search for `find` (free at https://www.etsy.com/developers/your-apps) |
| `FACEBOOK_COOKIE` | Logged-in Marketplace results: the `Cookie` header from your browser on facebook.com. Using it can get that account restricted. |

## How it's built

```
src/pricetracker/
  adapters/        one file per site; picks the adapter from the URL's domain
  history/         price-history providers (Keepa) for backfilling
  finder/          keyword search on eBay and Etsy, scored against eBay sold prices
  sinks/           outputs: console, CSV
  store.py         SQLite price table shared by live checks and history
  dashboard.py     HTML dashboard with charts
  checker.py       runs the checks
  cli.py           the `pricetracker` command
  toolkit.py       the same features as functions returning text
  mcp_server.py    MCP server wrapping toolkit.py, so Claude can use the tracker
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
