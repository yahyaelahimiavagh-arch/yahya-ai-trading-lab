"""YATL V3 wallet-intelligence foundations: offline, fail-closed, no provider calls.

This module NEVER selects real orders, sends Helius requests, or claims alpha.
V2's aggregate screening snapshots lack immutable point-in-time metadata and
historical as-of executable quotes. That absence must block V3 qualification.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

MIN_CLOSED = 50
MIN_ACTIVE_DAYS = 15
MIN_PARSE_RATIO = Decimal("0.8")
MIN_LIQUIDITY_USD = Decimal("20000")
REFERENCE_LATENCY_SECONDS = 134
MAX_SIGNAL_AGE_SECONDS = 300
MAX_QUOTE_AGE_SECONDS = 30
MAX_INPUT_BYTES = 16_000_000


def _nonnegative(value) -> Decimal | None:
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 else None
    except (TypeError, ValueError, InvalidOperation):
        return None


def _count(value) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _epoch(value) -> int | None:
    return value if type(value) is int and value > 0 else None


def _read(path: Path, expected: type):
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("offline input exceeds size cap")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, expected):
        raise ValueError("invalid offline input schema")
    return data


def _candidate_issues(row: dict, *, selection_at: int | None) -> list[str]:
    """Training-only checks. Missing evidence is rejection, not zero risk."""
    reasons = []
    if row.get("error"):
        reasons.append("provider_or_parser_error")
    if row.get("history_complete") is not True:
        reasons.append("incomplete_history")
    if row.get("meets_activity_thresholds") is not True:
        reasons.append("activity_or_basis_unverified")
    if _count(row.get("closed")) is None or row["closed"] < MIN_CLOSED:
        reasons.append("insufficient_closed_trades")
    if _count(row.get("active_days")) is None or row["active_days"] < MIN_ACTIVE_DAYS:
        reasons.append("insufficient_active_days")
    if _count(row.get("unmatched_sells")) != 0:
        reasons.append("unknown_cost_basis")
    parsed_total = _count(row.get("total_swaps_observed"))
    missed = _count(row.get("unparsed_swaps"))
    if parsed_total is None or parsed_total == 0 or missed is None or missed > parsed_total:
        reasons.append("missing_parse_coverage")
    elif Decimal(parsed_total - missed) / Decimal(parsed_total) < MIN_PARSE_RATIO:
        reasons.append("poor_parse_coverage")
    if row.get("copyable") is not True:
        reasons.append("copyability_not_established")
    liquidity = _nonnegative(row.get("min_liquidity_usd"))
    if liquidity is None or liquidity < MIN_LIQUIDITY_USD:
        reasons.append("liquidity_below_guard")
    if _nonnegative(row.get("net_realized_usd")) is None:
        reasons.append("positive_training_pnl_not_established")
    if selection_at is None:
        reasons.append("selection_cutoff_not_supplied")
    else:
        # A score computed after candidate selection may contain future data.
        screen_at = _epoch(row.get("screened_at"))
        history_end = _epoch(row.get("history_end_at"))
        if (screen_at is None or history_end is None
                or screen_at > selection_at or history_end > selection_at
                or history_end > screen_at):
            reasons.append("missing_or_leaky_training_timestamps")
    return reasons


def audit_screening(rows: list[dict], *, selection_at: int | None = None) -> dict:
    """Audit existing screening data; never output wallet IDs or rank alpha."""
    if not isinstance(rows, list):
        raise ValueError("screened data must be a JSON list")
    if selection_at is not None and _epoch(selection_at) is None:
        raise ValueError("positive selection timestamp required")
    rejected = Counter()
    candidates = []
    seen = set()
    duplicate_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            rejected["invalid_record"] += 1
            continue
        wallet = row.get("wallet")
        if not isinstance(wallet, str) or not wallet:
            rejected["missing_wallet_identifier"] += 1
            continue
        if wallet in seen:
            duplicate_rows += 1
            continue
        seen.add(wallet)
        issues = _candidate_issues(row, selection_at=selection_at)
        rejected.update(issues)
        if not issues:
            candidates.append(row)
    # Even qualified training candidates are NOT independently profitable.
    # SMART ranks by PRE-CUTOFF training PnL; the disjoint baseline is a
    # deterministic candidate-only control, not a randomized causal trial.
    num_each = min(4, len(candidates) // 2)
    smart = sorted(candidates, key=lambda r: (
        _nonnegative(r.get("net_realized_usd")) or Decimal(0),
        _nonnegative(r.get("preliminary_score")) or Decimal(0),
        r["wallet"]), reverse=True)[:num_each]
    smart_wallets = {r["wallet"] for r in smart}
    remaining = [r for r in candidates if r["wallet"] not in smart_wallets]
    control = sorted(remaining, key=lambda r: sha256(
        ("v3-control:" + r["wallet"]).encode("utf-8")).hexdigest())[:num_each]
    viable = num_each >= 2
    return {
        "kind": "YATL_V3_OFFLINE_SCREENING_AUDIT",
        "rows_seen": len(rows),
        "distinct_wallets_in_input": len(seen),
        "duplicate_wallet_rows": duplicate_rows,
        "training_candidates_with_point_in_time_proof": len(candidates),
        "overlapping_rejection_reasons": dict(sorted(rejected.items())),
        "selection_cutoff_supplied": selection_at is not None,
        "cohort_design": {
            "status": "candidate_only_not_alpha" if viable else "blocked_insufficient_evidence",
            "smart_candidates": len(smart) if viable else 0,
            "control_candidates": len(control) if viable else 0,
            "disjoint_by_construction": viable and not (
                smart_wallets & {r["wallet"] for r in control}),
            "balanced_or_randomized": False,
            "independent_forward_validation": False,
        },
        "warning": ("Current screening aggregates cannot establish 134-second "
                    "delayed execution PnL, true as-of liquidity, or forward alpha. "
                    "Never infer profitability from activity or V2's 1/3/10-second variants."),
    }


def audit_v2_report(report: dict) -> dict:
    """Aggregate retrospective V2 diagnostics; signal duplication kept explicit."""
    if report.get("kind") != "YATL_SMART_MONEY_PAPER_ONLY":
        raise ValueError("not a V2 paper-only report")
    blind = report.get("wallets_blind", [])
    smart = report.get("wallets_smart", [])
    if not isinstance(blind, list) or not isinstance(smart, list):
        raise ValueError("malformed cohort metadata")
    a = {w for w in blind if isinstance(w, str)}
    b = {w for w in smart if isinstance(w, str)}
    portfolios = report.get("portfolios", [])
    if not isinstance(portfolios, list):
        raise ValueError("malformed portfolio report")
    strategies = defaultdict(dict)
    unique_forward = set()
    delays = []
    counts = Counter()
    for p in portfolios:
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        if pid not in {f"{arm}_{d}s" for arm in ("blind", "smart", "consensus")
                       for d in (1, 3, 10)}:
            continue
        arm, delay_tag = pid.rsplit("_", 1)
        fills = p.get("fills", [])
        if not isinstance(fills, list):
            continue
        strategies[arm][delay_tag] = {
            "equity_usd": str(p.get("equity_usd")),
            "fills": len(fills),
            "halted": p.get("halted") is True,
        }
        counts["portfolio_fills"] += len(fills)
        counts["risk_exits"] += sum(
            f.get("side") == "RISK_EXIT" for f in fills if isinstance(f, dict))
        for fill in fills:
            if not isinstance(fill, dict) or fill.get("side") not in ("BUY", "SELL"):
                continue
            # Only count unique underlying events across cloned paper ledgers;
            # distinct strategies can execute the same leader event.
            identity = tuple(fill.get(k) for k in ("signature", "wallet", "mint", "side"))
            if any(not isinstance(part, str) or not part for part in identity):
                continue
            if identity in unique_forward:
                continue
            unique_forward.add(identity)
            lag = fill.get("signal_to_fill_seconds")
            if type(lag) is int and lag >= 0:
                delays.append(lag)
    indistinguishable = {}
    for arm in ("blind", "smart", "consensus"):
        d = strategies.get(arm, {})
        if len(d) == 3:
            identical = len({(x["equity_usd"], x["fills"]) for x in d.values()}) == 1
            indistinguishable[arm] = identical
    return {
        "kind": "YATL_V3_V2_BASELINE_AUDIT",
        "polls": _count(report.get("polls")),
        "unique_signals_reported": _count(report.get("unique_signals_seen")),
        "wallets_blind_count": len(a),
        "wallets_smart_count": len(b),
        "cohort_wallet_overlap_count": len(a & b),
        "paper_fill_rows_including_clones_and_risk_exits": counts["portfolio_fills"],
        "risk_exit_rows_including_clones": counts["risk_exits"],
        "unique_underlying_buy_sell_signals_with_fill": len(unique_forward),
        "median_observed_signal_to_fill_seconds": median(delays) if delays else None,
        "identical_1_3_10s_outcomes": indistinguishable,
        "interpretation": (
            "V2 has no independent randomized wallet control and no genuine "
            "1/3/10s latency experiment under 180s wallet polling. All results "
            "are hypothetical paper fills, not proven executable market returns."),
    }


def quote_coverage(events: list[dict], quotes: list[dict], *,
                   cutoff: int, latency_seconds: int = REFERENCE_LATENCY_SECONDS) -> dict:
    """Point-in-time quote COVERAGE on held-out live observations, not PnL.

    Never take the earliest quote AFTER the decision. Caller must supply
    real captured-at timestamps; current DEX prices cannot be backfilled.
    """
    if _epoch(cutoff) is None or not 0 <= latency_seconds <= 3600:
        raise ValueError("cutoff and latency must be valid")
    if not isinstance(events, list) or not isinstance(quotes, list):
        raise ValueError("events and quotes must be arrays")
    by_mint = defaultdict(list)
    for q in quotes:
        if not isinstance(q, dict) or q.get("source") != "live_recorded":
            continue
        mint, captured = q.get("mint"), _epoch(q.get("captured_at"))
        price, liquidity = _nonnegative(q.get("price_usd")), _nonnegative(q.get("liquidity_usd"))
        if isinstance(mint, str) and mint and captured and price is not None and price > 0 and liquidity is not None:
            by_mint[mint].append((captured, price, liquidity))
    times = {}
    for mint, rows in by_mint.items():
        rows.sort(key=lambda r: r[0])
        times[mint] = [r[0] for r in rows]
    counts = Counter()
    seen = set()
    eligible_latencies = []
    for event in events:
        if not isinstance(event, dict) or event.get("source") != "live_observed":
            counts["invalid_or_unverified_event"] += 1
            continue
        wallet, mint, sig, side = (event.get(field) for field in
                                   ("wallet", "mint", "signature", "side"))
        chain, observed = _epoch(event.get("chain_time")), _epoch(event.get("observed_at"))
        if (not all(isinstance(x, str) and x for x in (wallet, mint, sig))
                or side not in ("BUY", "SELL") or chain is None or observed is None
                or observed < chain):
            counts["invalid_or_unverified_event"] += 1
            continue
        key = (wallet, mint, sig, side)
        if key in seen:
            counts["duplicate_event"] += 1
            continue
        seen.add(key)
        if chain <= cutoff or observed <= cutoff:
            counts["before_holdout_cutoff"] += 1
            continue
        decision = max(observed, chain + latency_seconds)
        counts["holdout_events"] += 1
        if decision - chain > MAX_SIGNAL_AGE_SECONDS:
            counts["signal_too_old"] += 1
            continue
        rows = by_mint.get(mint, [])
        idx = bisect_right(times.get(mint, []), decision) - 1
        if idx < 0:
            counts["no_asof_quote"] += 1
            continue
        captured, price, liquidity = rows[idx]
        if decision - captured > MAX_QUOTE_AGE_SECONDS:
            counts["stale_asof_quote"] += 1
            continue
        if liquidity < MIN_LIQUIDITY_USD:
            counts["illiquid_at_decision"] += 1
            continue
        counts["indicative_quotes_available"] += 1
        eligible_latencies.append(decision - chain)
    return {
        "kind": "YATL_V3_FORWARD_QUOTE_COVERAGE_ONLY",
        "reference_latency_seconds": latency_seconds,
        "unique_holdout_events": counts["holdout_events"],
        "indicative_quotes_available": counts["indicative_quotes_available"],
        "coverage_fraction": (
            str(Decimal(counts["indicative_quotes_available"]) /
                Decimal(counts["holdout_events"]))
            if counts["holdout_events"] else None),
        "median_chain_to_decision_seconds_for_covered": (
            median(eligible_latencies) if eligible_latencies else None),
        "rejection_reasons": {k: v for k, v in sorted(counts.items())
                              if k != "indicative_quotes_available"},
        "realized_or_copy_pnl": None,
        "warning": ("Indicative point-in-time quote coverage, not achievable "
                    "execution or profitability. Requires genuine timestamped "
                    "historical snapshots and independent forward validation."),
    }


def run(*, screened: Path, report: Path | None = None,
        cutoff: int | None = None, events: Path | None = None,
        quotes: Path | None = None) -> dict:
    rows = _read(screened, list)
    result = {"schema": "YATL_V3_INTELLIGENCE_OFFLINE_V1",
              "screening": audit_screening(rows, selection_at=cutoff)}
    if report is not None:
        result["v2_baseline"] = audit_v2_report(_read(report, dict))
    if events is not None or quotes is not None:
        if events is None or quotes is None or cutoff is None:
            raise ValueError("events, quotes, and cutoff must all be provided")
        result["forward_quote_coverage"] = quote_coverage(
            _read(events, list), _read(quotes, list), cutoff=cutoff)
    else:
        result["forward_quote_coverage"] = {
            "status": "not_evaluated",
            "reason": "No independent timestamped holdout events and as-of quotes supplied",
            "realized_or_copy_pnl": None,
        }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="YATL V3 offline wallet-intelligence audit; never calls APIs or trades")
    parser.add_argument("--screened", required=True, type=Path)
    parser.add_argument("--report", type=Path, help="Read-only V2 paper report")
    parser.add_argument("--cutoff", type=int, help="Frozen selection/holdout Unix timestamp")
    parser.add_argument("--events", type=Path, help="Previously recorded forward events JSON")
    parser.add_argument("--quotes", type=Path, help="Previously recorded as-of quotes JSON")
    parser.add_argument("--output", type=Path, help="Optional SANITIZED V3 output file")
    args = parser.parse_args(argv)
    result = run(screened=args.screened, report=args.report,
                 cutoff=args.cutoff, events=args.events, quotes=args.quotes)
    payload = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)
    if args.output is None:
        print(payload)
    else:
        # Never write to a source input or active V2 report/state.
        target = args.output.resolve()
        sources = {p.resolve() for p in
                   (args.screened, args.report, args.events, args.quotes) if p is not None}
        if target in sources or target.name in ("state.json", "report.json", "helius_budget.json"):
            raise ValueError("refusing to overwrite live V2 source or budget")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temp = args.output.with_name(args.output.name + ".tmp")
        temp.write_text(payload + "\n", encoding="utf-8")
        temp.replace(args.output)
        print(json.dumps({"written": str(args.output), "kind": result["schema"]}))


if __name__ == "__main__":
    main()
