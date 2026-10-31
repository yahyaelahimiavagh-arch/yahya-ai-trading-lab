"""Offline screening diagnostics: aggregates only, no wallet addresses or API calls."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import json


def summarize(rows: list[dict], budget: dict | None = None) -> dict:
    if not isinstance(rows, list):
        raise ValueError("expected a screened JSON array")
    counts = Counter()
    failures = Counter()
    closed = []
    active = []
    liquidity = []
    for item in rows:
        if not isinstance(item, dict):
            failures["invalid_record"] += 1
            continue
        if item.get("error"):
            error = str(item["error"])
            # Never display free-text API errors, keys, URLs, or wallet addresses.
            if "429" in error:
                failures["provider_429_rate_limited"] += 1
            elif "403" in error:
                failures["provider_403_forbidden"] += 1
            elif "401" in error:
                failures["provider_401_unauthorized"] += 1
            elif "budget" in error.lower():
                failures["budget_blocked"] += 1
            else:
                failures["provider_or_parsing_error"] += 1
            continue
        counts["examined_without_error"] += 1
        if item.get("eligible") is True:
            counts["eligible"] += 1
        if item.get("history_complete") is True:
            counts["history_complete"] += 1
        else:
            failures["history_incomplete"] += 1
        if item.get("meets_activity_thresholds") is True:
            counts["meets_activity_thresholds"] += 1
        else:
            failures["below_activity_thresholds_or_unmatched"] += 1
        if int(item.get("unmatched_sells", 0)) > 0:
            failures["unmatched_sell_cost_basis"] += 1
        if item.get("copyable") is True:
            counts["passes_copyability_filter"] += 1
        else:
            failures["copyability_or_parse_quality"] += 1
        try:
            if int(item.get("closed", 0)) < 50:
                failures["fewer_than_50_closed_trades"] += 1
            if int(item.get("active_days", 0)) < 15:
                failures["fewer_than_15_active_days"] += 1
            if int(item.get("unparsed_swaps", 0)) > 0:
                counts["has_unparsed_swaps"] += 1
            if int(item.get("total_swaps_observed", 0)) > 0:
                counts["has_swaps"] += 1
            closed.append(int(item.get("closed", 0)))
            active.append(int(item.get("active_days", 0)))
            liquidity.append(float(item.get("min_liquidity_usd", 0)))
        except (ValueError, TypeError):
            failures["bad_metrics"] += 1
    budget = budget or {}
    n = budget.get("calls")
    if type(n) is not int or n < 0:
        n = None
    # Labels are independent conditions; overlapping counts do NOT sum to total.
    return {
        "screened_total": len(rows),
        "counts": dict(counts),
        "rejection_reasons_overlapping": dict(failures),
        "max_closed_trades_seen": max(closed, default=0),
        "max_active_days_seen": max(active, default=0),
        "max_min_liquidity_usd_seen": max(liquidity, default=0),
        "helius_requests_reserved_so_far": n,
        "helius_request_cap": 5000,
        "notes": "Diagnostic only. Does not change thresholds, buy/sell, or run API calls."
    }


def report_files(screened: Path, budget_file: Path) -> dict:
    rows = json.loads(screened.read_text(encoding="utf-8"))
    budget = json.loads(budget_file.read_text(encoding="utf-8")) if budget_file.exists() else {}
    return summarize(rows, budget)


def main():
    import argparse
    p = argparse.ArgumentParser(description="Offline YATL screening diagnostic; hides wallet addresses")
    p.add_argument("--screened", type=Path, default=Path("data/smart_money/screened.json"))
    p.add_argument("--budget", type=Path, default=Path("data/smart_money/helius_budget.json"))
    args = p.parse_args()
    print(json.dumps(report_files(args.screened, args.budget), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
