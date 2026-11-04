from decimal import Decimal

import pytest

from pricetracker.prices import parse_price


@pytest.mark.parametrize(
    "text, expected",
    [
        ("$1,299.99", "1299.99"),
        ("Now $429.00", "429.00"),
        ("1.299,99 €", "1299.99"),
        ("12,99", "12.99"),
        ("1,299", "1299"),
        ("$450", "450"),
        (49, "49"),
        (19.5, "19.5"),
        ("1 299,00 kr", "1299.00"),
    ],
)
def test_parse_price(text, expected):
    assert parse_price(text) == Decimal(expected)


@pytest.mark.parametrize("text", [None, "", "Out of stock"])
def test_parse_price_none(text):
    assert parse_price(text) is None
