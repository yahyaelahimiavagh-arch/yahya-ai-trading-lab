"""Canonical CRL-compatible candle admission; no interpolation or repair."""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from research.crisis_lab.acquisition import CanonicalRow, _canonical_csv, _validate_decimal

from .models import CADENCE_MS, OpportunityError, sha256


def validate_rows(rows: Sequence[CanonicalRow], interval: str, *, as_of_ms: int) -> str:
    if interval not in CADENCE_MS or not rows:
        raise OpportunityError("unsupported cadence or empty data")
    cadence = CADENCE_MS[interval]
    previous = -1
    for row in rows:
        if len(row.values) != 12:
            raise OpportunityError("canonical column count")
        try:
            opened, closed, trades = int(row.values[0]), int(row.values[6]), int(row.values[8])
            o, h, l, c, base, quote, taker_base, taker_quote = (
                _validate_decimal(row.values[i]) for i in (1, 2, 3, 4, 5, 7, 9, 10))
        except (ValueError, TypeError) as exc:
            raise OpportunityError("invalid canonical row") from exc
        if opened <= previous or opened % cadence or closed != opened + cadence - 1 or closed >= as_of_ms:
            raise OpportunityError("duplicate/nonmonotonic/incomplete candle")
        if min(o, h, l, c) <= 0 or h < max(o, c, l) or l > min(o, c, h):
            raise OpportunityError("invalid OHLC")
        if min(base, quote, taker_base, taker_quote) < Decimal(0) or trades < 0 or taker_base > base or taker_quote > quote:
            raise OpportunityError("invalid volume/trade count")
        previous = opened
    return sha256(_canonical_csv(rows))
