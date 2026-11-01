"""One-shot capped, read-only Helius probe; NEVER starts paper trading.

Use only after a failed paper pilot. Reports anonymous wallet indices and
bounded failure reason codes, not wallet addresses/signatures or API secrets.
This samples NOW; it cannot conclusively reconstruct an earlier failed poll.
No reports, experiment states, or portfolio balances are written.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

from .paper_copy_next import (
    MAX_HISTORY_PAGES, UnverifiableHistoryGap,
    _another_paper_runner_running, _budget, _bounded_wallet_history,
    _old_observer_running,
)
from .providers import Helius

MAX_REQUEST_ATTEMPTS = 18  # 6 wallets x 3 history pages; includes HTTP 429 retries


class CappedHelius(Helius):
    """Global hard cap includes retried HTTP calls, not just successful pages."""

    def __init__(self, api_key: str, limit: int = MAX_REQUEST_ATTEMPTS):
        super().__init__(api_key)
        self.request_attempts = 0
        self.limit = limit

    def _reserve_request(self):
        if self.request_attempts >= self.limit:
            raise RuntimeError("PROBE_ATTEMPT_CAP_REACHED")
        super()._reserve_request()
        self.request_attempts += 1


def probe(state: dict, helius: Helius) -> list[dict]:
    wallets = state.get("wallets")
    last_chain = state.get("last_seen_chain")
    started_at = state.get("started_at")
    if not (isinstance(wallets, list) and len(wallets) == 6
            and len(set(x for x in wallets if isinstance(x, str))) == 6
            and all(isinstance(x, str) and x for x in wallets)
            and isinstance(last_chain, dict)
            and type(started_at) is int and started_at > 0
            and state.get("state_status") == "halted_history_gap"):
        raise ValueError("requires six-wallet stopped history-gap state")
    results = []
    for index, wallet in enumerate(wallets, 1):
        cutoff = max(started_at, last_chain.get(wallet, 0))
        if type(cutoff) is not int or cutoff <= 0:
            raise ValueError("invalid source cutoff")
        try:
            rows, pages = _bounded_wallet_history(helius, wallet, cutoff=cutoff)
        except UnverifiableHistoryGap as exc:
            result = {"wallet_index": index, "outcome": "gap",
                      "reason": exc.reason,
                      "pages_fetched": exc.pages_fetched}
        except (RuntimeError, ValueError):
            result = {"wallet_index": index, "outcome": "provider_or_quota_stop",
                      "reason": "provider_or_attempt_cap", "pages_fetched": None}
        else:
            result = {"wallet_index": index, "outcome": "overlap_verified",
                      "reason": None, "pages_fetched": pages,
                      "rows_observed": len(rows)}
        results.append(result)
        if result["outcome"] == "provider_or_quota_stop":
            break
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-file", type=Path, required=True)
    p.add_argument("--budget-file", type=Path, required=True)
    p.add_argument("--run", action="store_true",
                   help="Make at most 18 existing-budget Helius HTTP attempts.")
    args = p.parse_args()
    state = json.loads(args.state_file.read_text(encoding="utf-8"))
    used, remaining = _budget(args.budget_file.expanduser().resolve())
    if state.get("state_status") != "halted_history_gap":
        raise SystemExit("Use the already halted history-gap state only")
    print(json.dumps({
        "mode": "one_shot_history_probe",
        "run": args.run, "max_request_attempts": MAX_REQUEST_ATTEMPTS,
        "budget_used_before": used, "budget_remaining_before": remaining,
        "caution": "Current on-chain sample; cannot reconstruct prior failed observation"
    }, sort_keys=True), flush=True)
    if not args.run:
        print("DRY_RUN_ONLY: zero API requests, no files changed.")
        return
    if _old_observer_running() or _another_paper_runner_running():
        raise SystemExit("Another Helius poller is running. No probe requests made.")
    if remaining < MAX_REQUEST_ATTEMPTS:
        raise SystemExit("Not enough existing reserved budget; no reset or purchase.")
    api = os.getenv("HELIUS_API_KEY", "")
    if not api:
        raise SystemExit("HELIUS_API_KEY not loaded; never paste it into chat")
    os.environ["YATL_SML_HELIUS_BUDGET_FILE"] = str(
        args.budget_file.expanduser().resolve())
    h = CappedHelius(api)
    results = probe(state, h)
    after_used, _ = _budget(args.budget_file.expanduser().resolve())
    print(json.dumps({
        "wallet_diagnostics": results,
        "request_attempts": h.request_attempts,
        "budget_used_after": after_used,
        "source_wallet_addresses_exported": 0,
        "real_orders": 0,
        "note": "Probe is read-only; original paper experiment remains stopped"
    }, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
