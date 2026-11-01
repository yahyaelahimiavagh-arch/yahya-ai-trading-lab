"""Whitelisted read-only adapter for the six-wallet PAPER COPY Hostinger dashboard.

Only aggregate simulated trading metrics are exported; never source wallet
addresses, transaction signatures, API credentials, or executable orders.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import time


def integer(value, default=0):
    return value if type(value) is int and value >= 0 else default


def amount(value):
    try:
        v = Decimal(str(value))
        return f"{v:.4f}" if v.is_finite() and v >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def signed_amount(value):
    """Decimal signed P/L; negative numbers are valid and must not disappear."""
    try:
        v = Decimal(str(value))
        return f"{v:.4f}" if v.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _wallet_rows(report: dict, positions: list) -> list[dict]:
    """Expose fixed-order aliases, never raw wallet addresses or signatures.

    Stats reflect fills of the ONE shared paper account, not independent P/L.
    The runner intentionally omits a top-level wallet list from its report;
    wallet identities appear solely as keys in per-wallet attribution.
    Sort those private keys for stable numbered aliases without exporting them.
    """
    summary = report.get("per_wallet_modeled_realized_pnl")
    if not isinstance(summary, dict) or len(summary) != 6:
        return []
    raw_wallets = report.get("wallets")
    wallets = sorted(summary) if raw_wallets is None else raw_wallets
    if not (isinstance(wallets, list) and len(wallets) == 6
            and all(isinstance(w, str) and bool(w) for w in wallets)
            and len(set(wallets)) == 6
            and set(wallets) == set(summary)):
        return []
    open_counts = {}
    for p in positions:
        if isinstance(p, dict) and isinstance(p.get("wallet"), str):
            w = p["wallet"]
            open_counts[w] = open_counts.get(w, 0) + 1
    result = []
    for index, wallet in enumerate(wallets, 1):
        metrics = summary.get(wallet)
        if not isinstance(metrics, dict):
            return []
        buys = integer(metrics.get("paper_buy_fills"))
        sells = integer(metrics.get("paper_leader_sell_fills"))
        risk = integer(metrics.get("paper_risk_exit_fills"))
        result.append({
            "alias": f"Wallet {index}",
            "source_signals": integer(metrics.get("source_signals")),
            "buy_fills": buys,
            "leader_sell_fills": sells,
            "risk_exit_fills": risk,
            "total_fills": buys + sells + risk,
            "open_positions": open_counts.get(wallet, 0),
            "open_position_cost_usd": amount(metrics.get("open_paper_position_cost_usd")),
            "modeled_realized_pnl_usd": signed_amount(metrics.get("modeled_realized_pnl_usd")),
        })
    return result


def build_paper_copy_status(report: dict | None, budget: dict | None, *,
                            now: int | None = None) -> dict:
    now = int(time.time()) if now is None else int(now)
    reserved = (budget or {}).get("calls")
    reserved = reserved if type(reserved) is int and 0 <= reserved <= 5000 else None
    base = {
        "status": "initializing", "mode": "exploratory_unvetted",
        "server_time": now, "updated_at": None, "started_at": None,
        "ends_at": None, "elapsed_seconds": 0, "progress_percent": 0,
        "wallets_followed": 0, "polls": 0, "signals_seen": 0,
        "paper_fills": 0, "open_positions": 0, "feed_complete": None,
        "api_requests_reserved": reserved, "api_safety_cap": 5000,
        "portfolios": [], "skips": {}, "recent_fills": [],
        "wallet_performance": [],
        "feed_health": {"state": "unknown", "collector_alive": None,
                        "expected_wallets": 0, "recent_wallets": 0,
                        "oldest_poll_age_seconds": None},
        "notice": "Waiting for a valid six-wallet paper-copy report.",
    }
    if not isinstance(report, dict) or report.get("kind") != "YATL_FORWARD_COPY_PAPER_REPORT":
        return base
    start = integer(report.get("started_at"))
    finish = integer(report.get("finish_at"))
    as_of = integer(report.get("as_of"))
    if not (0 < start < finish and as_of >= start and finish-start <= 6*3600):
        return base
    duration = finish - start
    elapsed = max(0, min(as_of-start, duration))
    old_status = report.get("experiment_status")
    if old_status == "completed":
        status = "completed"
    elif old_status == "interrupted":
        status = "interrupted"
    elif isinstance(old_status, str) and old_status.startswith("halted"):
        status = "degraded"
    elif old_status == "running":
        status = "stale" if as_of > now+45 or now-as_of > 660 else "running"
    else:
        status = "initializing"

    wallet_count = min(6, integer(report.get("watched_wallet_count")))
    recent_count = min(wallet_count, integer(report.get("last_polls_recent_count")))
    if status == "running":
        health_state = "polls_recent" if recent_count == wallet_count and wallet_count else "warming_up"
    elif status == "stale":
        health_state = "polls_stale"
    else:
        health_state = "unknown"

    raw_account = report.get("paper_account")
    account = raw_account if isinstance(raw_account, dict) else {}
    fills = account.get("fills")
    fills = fills if isinstance(fills, list) else []
    positions = account.get("open_positions")
    positions = positions if isinstance(positions, list) else []
    rejected = account.get("rejected")
    rejected = rejected if isinstance(rejected, dict) else {}
    cash, equity = amount(account.get("cash_usd")), amount(account.get("equity_usd"))
    pnl = str(Decimal(equity) - Decimal("1000")) if equity is not None else None
    portfolio = {
        "id": "paper_copy", "cash_usd": cash, "equity_usd": equity,
        "pnl_usd": pnl, "fills": len(fills), "open": len(positions),
        "halted": account.get("halted") is True,
        "rejected": sum(integer(x) for x in rejected.values()),
    }
    wallet_performance = _wallet_rows(report, positions)
    recent = []
    for fill in fills[-15:]:
        if not isinstance(fill, dict) or fill.get("side") not in ("BUY", "SELL", "RISK_EXIT"):
            continue
        mint = fill.get("mint")
        token = mint[:4] + "…" + mint[-4:] if isinstance(mint, str) and len(mint) >= 12 else "—"
        recent.append({
            "portfolio": "paper_copy", "side": fill["side"],
            "token": token, "time": integer(fill.get("time")),
            "usd_price": amount(fill.get("usd_price")),
        })
    raw_skips = report.get("skips")
    skips = raw_skips if isinstance(raw_skips, dict) else {}
    parse_count = sum(integer(v) for k, v in skips.items()
                      if isinstance(k, str) and k.startswith("parse_"))
    safe_skips = {
        "unparsed_or_unsupported": parse_count,
        "provider_failure": integer(skips.get("helius_poll_error")),
        "market_failure": integer(skips.get("market_quote_failure")),
        "sol_quote_unavailable": integer(skips.get("sol_price_unavailable")),
        "unverifiable_history_gap": integer(skips.get("unverifiable_100_tx_history_gap")),
        "helius_budget_exhausted": 0,
        "collector_stopped": 0,
        "historical_rows_ignored": integer(skips.get("historical_ignored")),
        "parse_missing_swap_event": integer(skips.get("parse_missing_swap_event")),
        "parse_ambiguous_legs": integer(skips.get("parse_ambiguous_legs")),
        "parse_unsupported_quote_pair": integer(skips.get("parse_unsupported_quote_pair")),
        "parse_missing_sol_reference_price": integer(skips.get("parse_missing_sol_reference_price")),
        "parse_invalid_amount_or_timestamp": integer(skips.get("parse_invalid_amount_or_timestamp")),
    }
    base.update({
        "status": status, "updated_at": as_of, "started_at": start,
        "ends_at": finish, "elapsed_seconds": elapsed,
        "progress_percent": round(100*elapsed/duration, 2),
        "wallets_followed": wallet_count, "polls": integer(report.get("cycles")),
        "signals_seen": integer(report.get("source_signals")),
        "paper_fills": len(fills), "open_positions": len(positions),
        "portfolios": [portfolio], "skips": safe_skips,
        "wallet_performance": wallet_performance,
        "recent_fills": list(reversed(recent)),
        "feed_health": {
            "state": health_state, "collector_alive": None,
            "expected_wallets": wallet_count, "recent_wallets": recent_count,
            "oldest_poll_age_seconds": None,
        },
        "notice": "Six unvetted candidate wallets; ONE $1,000 hypothetical paper account. No real orders or verified execution quotes.",
    })
    return base
