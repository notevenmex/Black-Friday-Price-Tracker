"""Helpers for turning price text into numbers."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_NUMBER = re.compile(r"\d[\d.,\s]*")


def parse_price(text: str | float | int | None) -> Decimal | None:
    """Parse a price like "$1,299.99", "1.299,99 €" or 49 into a Decimal.

    Returns None when no price can be found.
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return Decimal(str(text))

    match = _NUMBER.search(text)
    if not match:
        return None
    raw = re.sub(r"\s", "", match.group()).rstrip(".,")

    last_dot, last_comma = raw.rfind("."), raw.rfind(",")
    if last_dot != -1 and last_comma != -1:
        # Both present: whichever comes last is the decimal separator.
        if last_comma > last_dot:
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif last_comma != -1:
        # Only commas: "12,99" is a decimal, "1,299" is thousands.
        decimals = len(raw) - last_comma - 1
        if raw.count(",") == 1 and decimals in (1, 2):
            raw = raw.replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif raw.count(".") > 1:
        # "1.299.000" style thousands separators.
        raw = raw.replace(".", "")

    try:
        return Decimal(raw)
    except InvalidOperation:
        return None
