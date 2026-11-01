"""One-shot public Solana activity freshness scan over 26 frozen wallet candidates.

One rate-limited official RPC request per wallet; DOES NOT fetch trades, does
not rank profitability, and never touches Helius keys or request budget.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from .recent_wallet_receipts import BASE58, JUNE_END, PublicRpc, PublicRpcError, utc

MAX_WALLETS = 30
DAY = 86400


def assess(source: dict, rpc: PublicRpc, *, now: int) -> dict:
    if type(now) is not int or now < JUNE_END:
        raise ValueError("invalid as-of timestamp")
    candidates = source.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_WALLETS:
        raise ValueError("expected a bounded frozen wallet shortlist")
    seen = set()
    rows = []
    error = None
    for item in candidates:
        if not isinstance(item, dict):
            raise ValueError("invalid candidate")
        wallet = item.get("address")
        group = item.get("group")
        rank = item.get("rank")
        if (not isinstance(wallet, str) or not BASE58.fullmatch(wallet)
                or wallet in seen or type(group) is not int or group < 1
                or type(rank) is not int or rank < 1):
            raise ValueError("malformed or duplicate frozen candidate")
        seen.add(wallet)
        # Do not silently promote inaccessible wallets to "inactive".
        out = {"wallet": wallet, "historical_rank": rank,
               "training_behavior_group": group,
               "latest_confirmed_tx_utc": None, "days_since_latest": None,
               "recent_signature_count_in_sample": None,
               "signatures_after_june_in_sample": None,
               "status": "unverified"}
        rows.append(out)
        if error:
            out["status"] = "not_checked_rpc_unavailable"
            continue
        try:
            signatures = rpc.signatures(wallet)
        except PublicRpcError as exc:
            error = exc.code
            out["status"] = "rpc_unavailable"
            continue
        stamps = [row.get("blockTime") for row in signatures if isinstance(row, dict)]
        stamps = [x for x in stamps if type(x) is int]
        out["recent_signature_count_in_sample"] = len(signatures)
        out["signatures_after_june_in_sample"] = sum(x >= JUNE_END for x in stamps)
        if not stamps:
            out["status"] = "no_timestamped_transaction_in_latest_12"
            continue
        latest = max(stamps)
        out["latest_confirmed_tx_utc"] = utc(latest)
        out["days_since_latest"] = round((now-latest) / DAY, 3)
        if latest > now + 120:
            out["status"] = "clock_or_provider_timestamp_problem"
        elif latest >= now - 7 * DAY:
            out["status"] = "tx_within_7d_not_necessarily_trade"
        elif latest >= now - 30 * DAY:
            out["status"] = "tx_within_30d_not_necessarily_trade"
        elif latest >= JUNE_END:
            out["status"] = "only_older_post_june_activity_in_latest_12"
        else:
            out["status"] = "latest_observed_before_july"
    by_group = defaultdict(Counter)
    for row in rows:
        by_group[str(row["training_behavior_group"])][row["status"]] += 1
    return {
        "kind": "YATL_PUBLIC_SHORTLIST_FRESHNESS_V1",
        "as_of_utc": utc(now),
        "input_source": source.get("source"),
        "candidate_count": len(rows),
        "rpc_requests": rpc.requests,
        "rpc_error": error,
        "status_counts": dict(Counter(x["status"] for x in rows)),
        "status_by_training_behavior_group": {g: dict(v) for g, v in by_group.items()},
        "all_wallets": rows,
        "latest_7d_activity_only": [
            {"wallet": x["wallet"], "group": x["training_behavior_group"],
             "latest": x["latest_confirmed_tx_utc"]}
            for x in rows if x["status"] == "tx_within_7d_not_necessarily_trade"
        ],
        "warning": (
            "An on-chain signature does not prove a buy, sell, skill, profit, "
            "activity by the owner (it may be an unsolicited transfer), or "
            "copyability. The public endpoint has no historical completeness "
            "SLA. This is a bounded freshness filter only."),
        "helius_requests": 0,
        "realized_pnl": None,
    }


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidates", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args(argv)
    source = json.loads(args.candidates.read_text(encoding="utf-8"))
    result = assess(source, PublicRpc(), now=int(time.time()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(args.output.suffix+".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                              sort_keys=True)+"\n", encoding="utf-8")
    tmp.replace(args.output)
    print(json.dumps({
        "as_of": result["as_of_utc"],
        "input_count": result["candidate_count"],
        "rpc_requests": result["rpc_requests"],
        "rpc_error": result["rpc_error"],
        "status_counts": result["status_counts"],
        "status_by_group": result["status_by_training_behavior_group"],
        "active_last_week": result["latest_7d_activity_only"],
        "realized_pnl": None,
        "output": str(args.output)
    }, indent=2))


if __name__ == "__main__":
    main()
