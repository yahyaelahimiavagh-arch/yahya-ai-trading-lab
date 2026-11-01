"""Offline cohort-quality gate for the frozen Nov 1 six-wallet paper-copy sample.

Inputs are committed public/research evidence and a frozen selection manifest.
ZERO NETWORK, ZERO API, ZERO ORDERS. No source wallet addresses are printed.
This tool never promotes a research wallet into a trade authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WATCH = ROOT / "research/smart_money_lab/data/selected_forward_paper_wallets_20261101.json"
EVIDENCE = ROOT / "research/smart_money_lab/data/cohort_gate_evidence_20261101.json"

_ALLOWED_OUTCOMES = {
    "page_cap", "repeated_signature", "overlap_verified",
    "missing_signature", "invalid_timestamp"
}


def git_blob_sha1(content: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\\0" + content).hexdigest()


def audit(watch_bytes: bytes, evidence: dict) -> dict:
    """Return only anonymous, grounded results. Never predict unverified PnL."""
    if not isinstance(evidence, dict) or evidence.get("schema") != "YATL_SML_COHORT_GATE_EVIDENCE_V1":
        raise ValueError("invalid evidence schema")
    if git_blob_sha1(watch_bytes) != evidence.get("watchlist_git_blob_sha1"):
        raise ValueError("frozen watchlist blob SHA mismatch; refuse index mapping")
    watchlist = json.loads(watch_bytes)
    wallets = watchlist.get("wallets")
    if (watchlist.get("schema") != "YATL_FORWARD_PAPER_COPY_WATCHLIST_V1"
            or watchlist.get("allow_real_orders") is not False
            or not isinstance(wallets, list) or len(wallets) != 6):
        raise ValueError("expected original frozen six-wallet paper-only cohort")
    entries = evidence.get("wallets")
    if not (isinstance(entries, list) and len(entries) == 6
            and [x.get("index") if isinstance(x, dict) else None for x in entries] == list(range(1, 7))):
        raise ValueError("six fixed anonymous evidence entries required")
    results = []
    for rec in entries:
        n = rec.get("sampled_fifo_fragments")
        pages = rec.get("probe_pages")
        probe = rec.get("recent_probe")
        gross = rec.get("source_gross_sample")
        prints = rec.get("asof_prints_117s_30s")
        if (type(n) is not int or n < 0
                or type(pages) is not int or not 1 <= pages <= 3
                or probe not in _ALLOWED_OUTCOMES
                or gross not in ("negative", "unverified", "positive")
                or (prints is not None and (type(prints) is not int or not 0 <= prints <= n))):
            raise ValueError("invalid wallet evidence")
        reasons = []
        if probe != "overlap_verified":
            reasons.append("history_collection_not_verified")
        if gross == "negative":
            reasons.append("negative_partial_gross_sample")
        if n < 30:
            # This is a research sample-size floor, NOT independent closed trades.
            reasons.append("insufficient_sampled_fifo_fragments")
        if prints == 0:
            reasons.append("no_fresh_delayed_trade_print_pair")
        if evidence.get("full_wallet_trade_history_verified") is not True:
            reasons.append("complete_source_history_unverified")
        if evidence.get("realized_source_net_pnl_verified") is not True:
            reasons.append("source_net_pnl_unverified")
        if evidence.get("executable_follower_quote_verified") is not True:
            reasons.append("follower_executable_quotes_unverified")
        collection_category = (
            "REJECT_CURRENT_COLLECTOR" if probe != "overlap_verified" else
            "BORDERLINE_COLLECTION" if pages >= 3 else
            "ONE_PROBE_OVERLAP_ONLY"
        )
        results.append({
            "alias": f"Wallet {rec['index']}",
            "source_fragments_not_independent": n,
            "delayed_print_pairs_observed": prints,
            "partial_sample_gross": gross,
            "recent_probe_outcome": probe,
            "probe_pages": pages,
            "collector_category": collection_category,
            "candidate_for_live_copy": False,
            "candidate_for_new_six_hour_paper": False,
            "reasons": reasons,
        })
    return {
        "kind": "YATL_SIX_WALLET_COHORT_OFFLINE_GATE_V1",
        "data_date": evidence.get("study_date_utc"),
        "sample_class": "partial_nonrandom_four_pool_sample",
        "wallet_count": 6,
        "qualified_wallet_count": 0,
        "realized_source_pnl_verified": False,
        "executable_follower_quotes_verified": False,
        "new_helius_requests": 0,
        "new_paid_services": 0,
        "new_orders": 0,
        "decision": "NO_GO_NEW_PAPER_COHORT_OR_LIVE_TRADING",
        "recommendation": "Use archived public data for offline feasibility analysis first; do not extend the existing Helius experiment.",
        "wallets": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist", type=Path, default=WATCH)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    args = parser.parse_args(argv)
    outcome = audit(args.watchlist.read_bytes(),
                    json.loads(args.evidence.read_text(encoding="utf-8")))
    print(json.dumps(outcome, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
