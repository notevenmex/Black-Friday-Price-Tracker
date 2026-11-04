"""Sinks receive check results. Add new outputs (Google Sheets, email,
push alerts, ...) by implementing `Sink` and wiring it into the CLI."""

from __future__ import annotations

from typing import Protocol, Sequence

from ..models import PriceResult


class Sink(Protocol):
    def write(self, results: Sequence[PriceResult]) -> None: ...
