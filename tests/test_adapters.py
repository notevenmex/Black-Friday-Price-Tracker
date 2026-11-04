from decimal import Decimal

import pytest

from pricetracker.adapters import ExtractionError, get_adapter
from pricetracker.adapters.bestbuy import BestBuyAdapter, sku_from_url


@pytest.mark.parametrize(
    "url, name",
    [
        ("https://www.amazon.com/dp/B0CFPJYX7P", "amazon"),
        ("https://smile.amazon.co.uk/dp/B0CFPJYX7P", "amazon"),
        ("https://www.bestbuy.com/site/x/6505727.p?skuId=6505727", "bestbuy"),
        ("https://www.walmart.com/ip/x/123", "walmart"),
        ("https://www.microcenter.com/product/1/x", "microcenter"),
        ("https://sfbay.craigslist.org/search/sss?query=gpu", "craigslist"),
        ("https://www.facebook.com/marketplace/item/1", "facebook"),
        ("https://www.newegg.com/p/N82E1", "generic"),
        ("https://notamazon.com/dp/x", "generic"),
    ],
)
def test_get_adapter_by_domain(url, name):
    assert get_adapter(url).name == name


def test_get_adapter_by_name():
    assert get_adapter("https://anything.example", "generic").name == "generic"
    with pytest.raises(KeyError):
        get_adapter("https://anything.example", "nope")


def test_amazon(fixture_text):
    found = get_adapter("https://www.amazon.com/dp/X").extract(fixture_text("amazon.html"), "")
    assert found.price == Decimal("124.99")
    assert found.currency == "USD"
    assert found.title == "Kindle Paperwhite 16GB"


def test_amazon_captcha(fixture_text):
    with pytest.raises(ExtractionError, match="CAPTCHA"):
        get_adapter("https://www.amazon.com/dp/X").extract(fixture_text("amazon_captcha.html"), "")


def test_walmart(fixture_text):
    found = get_adapter("https://www.walmart.com/ip/1").extract(fixture_text("walmart.html"), "")
    assert found.price == Decimal("429.00")
    assert found.title == "Example Console Bundle"


def test_walmart_blocked(fixture_text):
    with pytest.raises(ExtractionError, match="bot check"):
        get_adapter("https://www.walmart.com/ip/1").extract(fixture_text("walmart_blocked.html"), "")


def test_microcenter_reads_content_attribute(fixture_text):
    found = get_adapter("https://www.microcenter.com/product/1").extract(fixture_text("microcenter.html"), "")
    assert found.price == Decimal("549.99")
    assert "RTX 5070" in found.title


def test_generic_json_ld_graph(fixture_text):
    found = get_adapter("https://shop.example").extract(fixture_text("generic_jsonld.html"), "")
    assert found.price == Decimal("139.00")
    assert found.currency == "USD"
    assert found.title == "Noise Cancelling Headphones"


def test_generic_meta_tags(fixture_text):
    found = get_adapter("https://shop.example").extract(fixture_text("generic_meta.html"), "")
    assert found.price == Decimal("39.95")
    assert found.title == "Gaming Mouse"


def test_generic_nothing_found():
    with pytest.raises(ExtractionError):
        get_adapter("https://shop.example").extract("<html><body>hi</body></html>", "")


def test_selector_adapter_falls_back_to_structured_data(fixture_text):
    # A Walmart page without the itemprop element but with JSON-LD.
    found = get_adapter("https://www.walmart.com/ip/1").extract(fixture_text("generic_jsonld.html"), "")
    assert found.price == Decimal("139.00")


@pytest.mark.parametrize(
    "url, sku",
    [
        ("https://www.bestbuy.com/site/sony-65/6505727.p?skuId=6505727", "6505727"),
        ("https://www.bestbuy.com/site/sony-65/6505727.p", "6505727"),
        ("https://www.bestbuy.com/product/sony/ABC/sku/6505727", "6505727"),
        ("https://www.bestbuy.com/site/searchpage.jsp?st=tv", None),
    ],
)
def test_bestbuy_sku_from_url(url, sku):
    assert sku_from_url(url) == sku


def test_bestbuy_builds_api_url():
    adapter = BestBuyAdapter(api_key="k3y")
    api = adapter.request_url("https://www.bestbuy.com/site/x/6505727.p?skuId=6505727")
    assert api.startswith("https://api.bestbuy.com/v1/products/6505727.json?apiKey=k3y")


def test_bestbuy_requires_key(monkeypatch):
    monkeypatch.delenv("BESTBUY_API_KEY", raising=False)
    with pytest.raises(ExtractionError, match="BESTBUY_API_KEY"):
        BestBuyAdapter().request_url("https://www.bestbuy.com/site/x/6505727.p")


def test_bestbuy_parses_api_response(fixture_text):
    found = BestBuyAdapter(api_key="k").extract(fixture_text("bestbuy_api.json"), "")
    assert found.price == Decimal("899.99")
    assert found.title.startswith("Sony")


def test_craigslist_search(fixture_text):
    url = "https://sfbay.craigslist.org/search/sss?query=rtx+4080"
    listings = get_adapter(url).extract_listings(fixture_text("craigslist_search.html"), url)
    assert [l.price for l in listings] == [Decimal("650"), Decimal("1400"), None]
    assert listings[0].title == "RTX 4080 Founders Edition"
    assert listings[0].location == "mission district"
    assert listings[1].url == "https://sfbay.craigslist.org/eby/sys/d/gaming-pc/7790000002.html"


def test_craigslist_posting(fixture_text):
    url = "https://sfbay.craigslist.org/eby/vgm/d/ps5/1.html"
    found = get_adapter(url).extract(fixture_text("craigslist_posting.html"), url)
    assert found.price == Decimal("325") and found.title == "Used PS5 disc edition"


def test_facebook_search_dedupes_listings(fixture_text):
    url = "https://www.facebook.com/marketplace/sanfrancisco/search?query=ps5"
    listings = get_adapter(url).extract_listings(fixture_text("facebook_search.html"), url)
    assert [(l.title, l.price) for l in listings] == [
        ("PS5 Slim bundle", Decimal("350.00")), ("PS5 controller", Decimal("40.00"))]
    assert listings[0].url == "https://www.facebook.com/marketplace/item/1111/"
    assert listings[0].location == "Oakland, CA"


def test_facebook_item_picks_matching_id(fixture_text):
    url = "https://www.facebook.com/marketplace/item/2222/"
    found = get_adapter(url).extract(fixture_text("facebook_search.html"), url)
    assert found.price == Decimal("40.00") and found.currency == "USD"


def test_facebook_login_wall(fixture_text):
    url = "https://www.facebook.com/marketplace/item/1/"
    with pytest.raises(ExtractionError, match="FACEBOOK_COOKIE"):
        get_adapter(url).extract(fixture_text("facebook_login.html"), url)


def test_facebook_sends_cookie(monkeypatch):
    monkeypatch.setenv("FACEBOOK_COOKIE", "c_user=1; xs=2")
    assert get_adapter("https://www.facebook.com/marketplace/").request_headers() == {"Cookie": "c_user=1; xs=2"}
