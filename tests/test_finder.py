import json
from decimal import Decimal

import pytest

from pricetracker import cli
from pricetracker.finder import EbaySource, EtsySource, Finder, SeenStore, SourceError, make_spec
from pricetracker.finder.ebay import BROWSE_URL, EbayAuth, INSIGHTS_URL, TOKEN_URL
from pricetracker.finder.etsy import SEARCH_URL as ETSY_URL
from pricetracker.finder.models import GREAT, HIGH, SUSPICIOUS, MarketListing, SoldComp
from pricetracker.finder.scoring import is_relevant, market_value, score
from pricetracker.watchlist import WatchlistError


class FakeClient:
    """Answers by URL; `fail` maps a URL to an HTTP status to raise."""

    def __init__(self, routes, fail=None):
        self.routes, self.fail, self.calls = routes, fail or {}, []

    def get(self, url, params=None, headers=None):
        self.calls.append(("GET", url, params, headers))
        if url in self.fail:
            raise SourceError(f"HTTP {self.fail[url]}", status=self.fail[url])
        return self.routes[url]

    def post_form(self, url, data, auth=None):
        self.calls.append(("POST", url, data, auth))
        return {"access_token": "tok-" + data["scope"].rsplit("/", 1)[-1], "expires_in": 7200}


@pytest.fixture
def load_json(fixture_text):
    return lambda name: json.loads(fixture_text(name))


@pytest.fixture
def client(load_json):
    return FakeClient({BROWSE_URL: load_json("ebay_browse.json"), INSIGHTS_URL: load_json("ebay_sold.json"),
                       ETSY_URL: load_json("etsy_search.json")})


def make_finder(client, seen=None):
    ebay = EbaySource(client, EbayAuth(client, "id", "secret"))
    etsy = EtsySource(client, api_key="etsykey")
    return Finder([ebay, etsy], seen=seen)


JERSEY = dict(exclude="replica,custom")


# --- relevance -------------------------------------------------------------

def test_relevance_requires_all_keywords_and_respects_excludes():
    spec = make_spec(None, "travis scott jersey", exclude="replica, kids")
    assert is_relevant("Travis Scott Cactus Jack Jersey", spec)
    assert is_relevant("TRAVIS SCOTT jerseys bundle", spec)  # plural ok
    assert not is_relevant("Travis Scott poster", spec)
    assert not is_relevant("Travis Scott jersey replica", spec)
    assert not is_relevant("Travis Scott jersey KIDS size", spec)
    assert is_relevant("Travis Scott poster", make_spec(None, "travis scott jersey", match="any"))


def test_exclude_phrase_matches_words_in_order():
    spec = make_spec(None, "jersey", exclude=["patch only"])
    assert not is_relevant("Astros jersey patch only", spec)
    assert is_relevant("Astros jersey, only patch is on the sleeve", spec)


# --- market value and scoring ---------------------------------------------

def test_market_value_from_sold_drops_outliers_and_irrelevant():
    spec = make_spec(None, "travis scott jersey")
    sold = [SoldComp("Travis Scott jersey", Decimal(p)) for p in ("130", "140", "150", "165", "1400")]
    sold.append(SoldComp("Travis Scott vinyl", Decimal("40")))
    mv = market_value(spec, sold)
    assert mv.basis == "ebay-sold" and mv.price == Decimal("145.00") and mv.sample_size == 4


def test_market_value_falls_back_to_asking_then_none():
    spec = make_spec(None, "jersey")
    asking = [MarketListing("ebay", str(i), "jersey", Decimal(p)) for i, p in enumerate(("100", "120", "140"))]
    assert market_value(spec, [], asking).basis == "ebay-asking"
    assert market_value(spec, [], asking[:2]) is None
    assert market_value(make_spec(None, "jersey", reference_price=200)).basis == "manual"


def test_score_verdicts():
    spec = make_spec(None, "jersey", max_price=60)
    mv = market_value(make_spec(None, "x", reference_price=100))
    def s(price):
        return score(MarketListing("ebay", "1", "jersey", Decimal(price)), spec, mv)
    assert s("70").verdict == GREAT and s("70").is_deal
    assert s("120").verdict == HIGH and not s("120").is_deal
    assert s("30").verdict == SUSPICIOUS and s("30").is_deal
    assert s("95").discount == Decimal("0.050")
    # under max_price counts as a deal even without a market value
    assert score(MarketListing("ebay", "1", "jersey", Decimal("50")), spec, None).is_deal


def test_threshold_given_as_percent():
    assert make_spec(None, "x", deal_threshold=30).deal_threshold == Decimal("0.3")
    with pytest.raises(WatchlistError):
        make_spec(None, "  ")


# --- sources ---------------------------------------------------------------

def test_ebay_parses_listings_and_sends_filters(client):
    ebay = EbaySource(client, EbayAuth(client, "id", "secret"))
    spec = make_spec(None, "travis scott jersey", max_price=200, condition="used")
    listings = {l.listing_id: l for l in ebay.search(spec)}
    first = listings["v1|1001|0"]
    assert first.price == Decimal("95.00") and first.shipping == Decimal("5.00") and first.total == Decimal("100.00")
    assert first.image_url.endswith("s-l500.jpg") and first.seller == "jerseyguy"
    auction = listings["v1|1004|0"]
    assert auction.price == Decimal("40.00") and auction.buying_option == "auction" and auction.ends_at
    _, url, params, headers = client.calls[-1]
    assert params["filter"] == "price:[..200],priceCurrency:USD,conditions:{USED}"
    assert headers["Authorization"] == "Bearer tok-api_scope"
    assert headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US"


def test_ebay_token_is_cached(client):
    auth = EbayAuth(client, "id", "secret")
    auth.token(); auth.token()
    assert sum(1 for c in client.calls if c[1] == TOKEN_URL) == 1


def test_ebay_without_keys(monkeypatch):
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    ebay = EbaySource(FakeClient({}))
    assert not ebay.configured
    with pytest.raises(SourceError, match="EBAY_CLIENT_ID"):
        ebay.search(make_spec(None, "x"))


def test_etsy_parses_price_and_unescapes_title(client):
    listings = EtsySource(client, api_key="k", shared_secret="s").search(make_spec(None, "travis scott jersey"))
    assert listings[0].price == Decimal("85.00") and '"Astroworld"' in listings[0].title
    assert client.calls[-1][3] == {"x-api-key": "k:s"}


# --- end to end ------------------------------------------------------------

def test_finder_end_to_end(client):
    result = make_finder(client).find(make_spec(None, "travis scott jersey", **JERSEY))
    assert result.market.basis == "ebay-sold" and result.market.price == Decimal("145.00")
    ids = [s.listing.listing_id for s in result.listings]
    assert "v1|1003|0" not in ids  # replica excluded
    assert "v1|1005|0" not in ids  # poster isn't a jersey
    assert "3002" not in ids  # custom excluded
    top = result.listings[0]
    assert top.is_deal
    by_id = {s.listing.listing_id: s for s in result.listings}
    assert by_id["v1|1001|0"].verdict == GREAT  # $100 vs $145
    assert by_id["v1|1004|0"].verdict == GREAT  # $40 bid: auction, not suspicious
    assert by_id["v1|1002|0"].verdict == HIGH
    assert result.errors == []


def test_finder_falls_back_when_sold_prices_refused(load_json):
    client = FakeClient({BROWSE_URL: load_json("ebay_browse.json"), ETSY_URL: load_json("etsy_search.json")},
                        fail={INSIGHTS_URL: 403})
    finder = make_finder(client)
    result = finder.find(make_spec(None, "travis scott jersey", **JERSEY))
    assert result.market.basis == "ebay-asking"
    assert "Marketplace Insights" in finder.sold_unavailable
    finder.find(make_spec(None, "travis scott jersey"))
    assert sum(1 for c in client.calls if c[1] == INSIGHTS_URL) == 1  # not asked again


def test_finder_reports_unknown_and_unconfigured_sites(client, monkeypatch):
    monkeypatch.delenv("ETSY_API_KEY", raising=False)
    finder = Finder([EbaySource(client, EbayAuth(client, "id", "secret")), EtsySource(client)])
    result = finder.find(make_spec(None, "travis scott jersey", sites="ebay,etsy,grailed"))
    assert any("grailed" in e for e in result.errors)
    assert any("ETSY_API_KEY" in e for e in result.errors)
    assert result.listings  # eBay still searched


def test_seen_store_marks_new_listings(client, tmp_path):
    seen = SeenStore(tmp_path / "p.db")
    finder = make_finder(client, seen)
    spec = make_spec("Travis jersey", "travis scott jersey", **JERSEY)
    assert all(s.is_new for s in finder.find(spec).listings)
    assert not any(s.is_new for s in finder.find(spec).listings)
    assert seen.prices.history("search:Travis jersey")[0].source == "ebay-sold"
    seen.close()


# --- CLI -------------------------------------------------------------------

def test_cli_find_from_watchlist(tmp_path, monkeypatch, capsys, client):
    monkeypatch.setattr("pricetracker.finder.runner.default_sources",
                        lambda: [EbaySource(client, EbayAuth(client, "id", "secret")),
                                 EtsySource(client, api_key="k")])
    wl = tmp_path / "w.toml"
    wl.write_text('[[search]]\nname = "Travis Scott jersey"\nkeywords = "travis scott jersey"\n'
                  'exclude = ["replica", "custom"]\nmax_price = 120\n')
    html_path = tmp_path / "finds.html"
    assert cli.main(["-w", str(wl), "find", "--db", str(tmp_path / "p.db"), "--html", str(html_path)]) == 0
    out = capsys.readouterr().out
    assert "== Travis Scott jersey ==" in out
    assert "Market value: $145.00 (median eBay sold price" in out
    assert "[DEAL ] $95.00 + $5.00 ship  eBay" in out
    page = html_path.read_text()
    assert "Great deal" in page and "https://www.ebay.com/itm/1001" in page

    assert cli.main(["-w", str(wl), "find", "--db", str(tmp_path / "p.db"), "--new-only"]) == 0
    assert "Nothing new to show." in capsys.readouterr().out


def test_cli_find_needs_keywords_or_searches(tmp_path, capsys):
    wl = tmp_path / "w.toml"
    wl.write_text("")
    assert cli.main(["-w", str(wl), "find"]) == 2
    assert "no [[search]] entries" in capsys.readouterr().err
    assert cli.main(["-w", str(wl), "find", "x", "--new-only"]) == 2
