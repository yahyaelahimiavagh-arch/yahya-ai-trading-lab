"""Select a clearly UNVETTED observation cohort from existing cached screening data.

This is a paper-only telemetry pilot, never a substitute for smart-money vetting.
No calls to data providers, no signatures, no order execution.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation


def _numeric(row: dict, field: str) -> Decimal:
    try:
        n = Decimal(str(row.get(field, 0)))
        return n if n.is_finite() and n >= 0 else Decimal(0)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)


def exploratory_watchlist(records: list[dict], *, per_arm: int = 4) -> tuple[list[str], list[str]]:
    """Two independent, descriptive *provisional* watchlists.

    Exclude API-failed, incomplete-history, no-swap, and no-closed-trade rows.
    This deliberately does not certify profitability, parse completeness,
    copyability or inferred alpha. Real-time fills retain original >=$20k
    token liquidity guard. A strict cohort is always preferred to this one.
    """
    if not (1 <= per_arm <= 4) or not isinstance(records, list):
        raise ValueError("invalid exploratory watchlist parameters")
    candidates = []
    seen = set()
    for row in records:
        if not isinstance(row, dict) or row.get("error"):
            continue
        wallet = row.get("wallet")
        if not isinstance(wallet, str) or wallet in seen:
            continue
        seen.add(wallet)
        if (row.get("history_complete") is not True
                or _numeric(row, "closed") < 1
                or _numeric(row, "total_swaps_observed") < 1):
            continue
        candidates.append(row)
    # Historical activity is NOT equivalent to skill. This is a baseline.
    activity = sorted(candidates,
                      key=lambda r: (_numeric(r, "closed"),
                                     _numeric(r, "active_days"), r["wallet"]), reverse=True)
    # Current liquidity is only a viability proxy, not a buy recommendation.
    liquidity = sorted(candidates,
                       key=lambda r: (_numeric(r, "min_liquidity_usd"),
                                      _numeric(r, "active_days"), r["wallet"]), reverse=True)
    if len(candidates) < 2:
        raise ValueError("fewer than two complete-history exploratory wallets; do not bypass")
    return [r["wallet"] for r in activity[:per_arm]], [r["wallet"] for r in liquidity[:per_arm]]
