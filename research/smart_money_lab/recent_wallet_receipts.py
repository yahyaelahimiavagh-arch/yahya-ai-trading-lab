"""Read-only bounded Solana public RPC verification of 3 HISTORICAL wallet groups.

Uses only Solana official public endpoint: https://api.mainnet.solana.com
Only getSignaturesForAddress + getTransaction; no keys, Helius, RPC providers,
orders, transaction submission, continuous workers or subscription.
Source-wallet trading skill and follower profitability are NOT computed.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import json
import re
import time
import urllib.error
import urllib.request

ENDPOINT = "https://api.mainnet.solana.com"
BASE58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
SIGNATURE58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{80,90}$")
JUNE_END = 1782864000  # 2026-07-01T00:00:00Z
MAX_SIGNATURES = 12
MAX_TX_PER_WALLET = 12
MAX_REQUESTS = 45
REQUEST_INTERVAL_SECONDS = 2.0
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
STABLECOINS = {USDC: "USDC", USDT: "USDT"}

WALLETS = {
    "behavior_group_1": "4VKQr6DLKpP6DpEp8xbr6nTWRCUcTP6bXVGfEA6jxRYb",
    "behavior_group_2": "55C9XKGpi7d81MnKHvKVp9tKPvm2vHbEYgaCM7XQhLh1",
    "behavior_group_3": "7XCSydTBzEcz1M2PpvM6EauSEKpnDztxbDjAXxmdYdHU",
}


def utc(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if type(ts) is int else None


class PublicRpcError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__("public RPC unavailable")


class PublicRpc:
    def __init__(self):
        self.requests = 0
        self._last_monotonic = None

    def call(self, method: str, params: list):
        if method not in ("getSignaturesForAddress", "getTransaction"):
            raise ValueError("method forbidden by read-only research policy")
        if self.requests >= MAX_REQUESTS:
            raise PublicRpcError("safety_cap")
        if self._last_monotonic is not None:
            wait = REQUEST_INTERVAL_SECONDS - (time.monotonic()-self._last_monotonic)
            if wait > 0:
                time.sleep(wait)
        body = json.dumps({
            "jsonrpc": "2.0", "id": self.requests + 1,
            "method": method, "params": params,
        }).encode("utf-8")
        req = urllib.request.Request(ENDPOINT, data=body, headers={
            "Content-Type": "application/json",
            "User-Agent": "YATL-readonly-wallet-evidence/1",
        }, method="POST")
        self._last_monotonic = time.monotonic()
        self.requests += 1
        try:
            with urllib.request.urlopen(req, timeout=15) as result:
                raw = result.read(4_000_001)
        except urllib.error.HTTPError as e:
            raise PublicRpcError(f"http_{e.code}") from None
        except (OSError, urllib.error.URLError):
            raise PublicRpcError("network_unavailable") from None
        if len(raw) > 4_000_000:
            raise PublicRpcError("response_too_large")
        try:
            answer = json.loads(raw)
        except (ValueError, UnicodeError):
            raise PublicRpcError("invalid_json") from None
        if not isinstance(answer, dict) or answer.get("error") is not None:
            err = answer.get("error") if isinstance(answer, dict) else None
            code = err.get("code") if isinstance(err, dict) else "invalid_reply"
            raise PublicRpcError(f"rpc_{code}")
        return answer.get("result")

    def signatures(self, wallet):
        if not isinstance(wallet, str) or not BASE58.fullmatch(wallet):
            raise ValueError("invalid source-wallet address")
        result = self.call("getSignaturesForAddress", [wallet, {
            "limit": MAX_SIGNATURES, "commitment": "finalized",
        }])
        if not isinstance(result, list):
            raise PublicRpcError("malformed_signatures")
        return result

    def transaction(self, signature):
        if not isinstance(signature, str) or not SIGNATURE58.fullmatch(signature):
            raise ValueError("invalid transaction signature")
        return self.call("getTransaction", [signature, {
            "commitment": "finalized", "encoding": "jsonParsed",
            "maxSupportedTransactionVersion": 0,
        }])


def _amount(row):
    if not isinstance(row, dict):
        return None
    ix = row.get("accountIndex")
    mint = row.get("mint")
    data = row.get("uiTokenAmount")
    if type(ix) is not int or not isinstance(mint, str) or not isinstance(data, dict):
        return None
    decimals = data.get("decimals")
    raw = data.get("amount")
    if (type(decimals) is not int or not 0 <= decimals <= 18 or
            not isinstance(raw, str) or not raw.isdecimal() or len(raw) > 40):
        return None
    return ix, mint, decimals, int(raw)


def owned_token_deltas(meta: dict, wallet: str) -> tuple[dict, dict]:
    """Integer exact SPL token changes for wallet-owned token-account indexes.

    Do not infer ownership from token account presence alone; fail closed when
    meta owner mappings are absent/contradictory.
    """
    before, after = meta.get("preTokenBalances"), meta.get("postTokenBalances")
    if not isinstance(before, list) or not isinstance(after, list):
        return {}, {"token_balance_metadata_missing": True}
    rows = [(row, "pre") for row in before] + [(row, "post") for row in after]
    owned = set()
    errors = Counter()
    for row, _ in rows:
        parsed = _amount(row)
        if parsed is None:
            errors["invalid_token_balance_row"] += 1
            continue
        if row.get("owner") == wallet:
            owned.add((parsed[0], parsed[1]))
    pre_d = defaultdict(int)
    post_d = defaultdict(int)
    decimals_by_mint = {}
    for row, stage in rows:
        data = _amount(row)
        if data is None:
            continue
        ix, mint, decimals, amount = data
        if (ix, mint) not in owned:
            continue
        row_owner = row.get("owner")
        if row_owner is not None and row_owner != wallet:
            errors["ownership_conflict"] += 1
            continue
        if mint in decimals_by_mint and decimals_by_mint[mint] != decimals:
            errors["decimal_conflict"] += 1
            continue
        decimals_by_mint[mint] = decimals
        (pre_d if stage == "pre" else post_d)[(ix, mint)] += amount
    changes = defaultdict(int)
    for key in owned:
        ix, mint = key
        changes[mint] += post_d.get(key, 0) - pre_d.get(key, 0)
    if errors.get("ownership_conflict") or errors.get("decimal_conflict"):
        return {}, dict(errors)
    result = {}
    for mint, raw in changes.items():
        if raw:
            decimals = decimals_by_mint[mint]
            qty = Decimal(raw) / (Decimal(10) ** decimals)
            result[mint] = {
                "raw_delta": str(raw), "decimals": decimals,
                "token_delta": str(qty),
            }
    return result, dict(errors)


def interpret_transaction(tx, wallet: str, signature: str) -> dict:
    """Classify exact owner-balance delta; do NOT claim confirmed swap or PnL."""
    if not isinstance(tx, dict):
        return {"signature": signature, "status": "tx_unavailable"}
    meta = tx.get("meta")
    stamp = tx.get("blockTime")
    if not isinstance(meta, dict):
        return {"signature": signature, "status": "missing_transaction_metadata"}
    if meta.get("err") is not None:
        return {"signature": signature, "status": "transaction_failed"}
    delta, warnings = owned_token_deltas(meta, wallet)
    row = {
        "signature": signature,
        "slot": tx.get("slot") if type(tx.get("slot")) is int else None,
        "block_time": stamp if type(stamp) is int else None,
        "block_time_utc": utc(stamp),
        "status": "unclassified",
        "owner_token_deltas": delta,
        "balance_metadata_warnings": warnings,
        "network_fee_lamports": meta.get("fee") if type(meta.get("fee")) is int else None,
    }
    if not delta:
        row["status"] = "no_verifiable_owned_spl_change"
        return row
    stable = [(m, Decimal(x["token_delta"])) for m, x in delta.items() if m in STABLECOINS]
    other = [(m, Decimal(x["token_delta"])) for m, x in delta.items() if m not in STABLECOINS]
    if len(stable) != 1 or len(other) != 1 or stable[0][1] * other[0][1] >= 0:
        row["status"] = "multileg_or_nonstable_flow_no_pnl"
        return row
    quote_mint, stable_delta = stable[0]
    token_mint, token_delta = other[0]
    row["status"] = "simple_opposite_stablecoin_token_flow_unverified_swap_intent"
    row["direction"] = "BUY_CANDIDATE" if token_delta > 0 else "SELL_CANDIDATE"
    row["token_mint"] = token_mint
    row["token_amount"] = str(abs(token_delta))
    row["stablecoin"] = STABLECOINS[quote_mint]
    row["nominal_stablecoin_amount"] = str(abs(stable_delta))
    row["price_per_token_stablecoin"] = str(abs(stable_delta/token_delta))
    return row


def audit(wallets: dict[str, str], rpc: PublicRpc, *, since: int = JUNE_END) -> dict:
    if type(since) is not int or since <= 0:
        raise ValueError("invalid historical cutoff")
    groups = {}
    parsed_transactions = {}
    summary = Counter()
    sig_to_group = defaultdict(set)
    blocked_reason = None
    for group, wallet in wallets.items():
        result = {
            "wallet": wallet, "latest_known_signature_utc": None,
            "latest_signature_count": 0,
            "recent_signatures_after_cutoff": 0,
            "sample_reaches_past_cutoff": False,
            "recent_transactions": [],
            "outcome": "not_checked",
        }
        groups[group] = result
        try:
            signatures = rpc.signatures(wallet)
        except PublicRpcError as e:
            blocked_reason = e.code
            result["outcome"] = "public_rpc_unavailable"
            break
        result["latest_signature_count"] = len(signatures)
        if signatures:
            first = signatures[0].get("blockTime")
            result["latest_known_signature_utc"] = utc(first)
            last = signatures[-1].get("blockTime")
            result["sample_reaches_past_cutoff"] = type(last) is int and last < since
        recent = []
        for record in signatures:
            if not isinstance(record, dict):
                continue
            stamp, sig = record.get("blockTime"), record.get("signature")
            if (type(stamp) is int and stamp >= since and
                    isinstance(sig, str) and SIGNATURE58.fullmatch(sig)):
                recent.append(sig)
                sig_to_group[sig].add(group)
        result["recent_signatures_after_cutoff"] = len(recent)
        for signature in recent[:MAX_TX_PER_WALLET]:
            if signature not in parsed_transactions:
                try:
                    tx = rpc.transaction(signature)
                except PublicRpcError as e:
                    blocked_reason = e.code
                    break
                parsed_transactions[signature] = tx
            interpretation = interpret_transaction(parsed_transactions[signature], wallet, signature)
            result["recent_transactions"].append(interpretation)
            summary[interpretation["status"]] += 1
        result["outcome"] = ("public_rpc_unavailable" if blocked_reason else
                             "sample_truncated" if
                             len(signatures) == MAX_SIGNATURES and
                             not result["sample_reaches_past_cutoff"] else
                             "sampled_until_cutoff")
        if blocked_reason:
            break
    shared = [
        {"signature": sig, "groups": sorted(group_set)}
        for sig, group_set in sig_to_group.items() if len(group_set) > 1
    ]
    return {
        "kind": "YATL_RECENT_WALLET_CHAIN_EVIDENCE_V1",
        "public_rpc": ENDPOINT,
        "cutoff_utc": utc(since),
        "wallet_groups": groups,
        "distinct_tx_signatures_retrieved": len(parsed_transactions),
        "reused_signatures_across_groups": shared,
        "transaction_classification_counts": dict(summary),
        "rpc_request_count": rpc.requests,
        "rpc_error": blocked_reason,
        "read_only": True,
        "helius_requests": 0,
        "no_realized_pnl": True,
        "missing_evidence": [
            "incomplete source wallet inventory and transfer history",
            "native SOL historical USD conversion and network fee USD valuation",
            "complex routed swaps, unknown balance ownership and inner instructions",
            "complete past episode cost basis and sell execution history",
            "follower route quote, latency, slippage and real transaction execution",
        ],
        "warning": (
            "Recent public-chain token account balance changes are not proof of "
            "trader skill, profit, swap route or executable follower returns. "
            "Only up to the 12 most recent signatures per wallet are sampled. "
            "Do not infer inactivity from empty parsed swap counts."),
    }


def main(argv=None):
    import argparse
    from pathlib import Path
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--since", type=int, default=JUNE_END)
    args = p.parse_args(argv)
    result = audit(WALLETS, PublicRpc(), since=args.since)
    # No private keys, tokens, env vars, or untrusted response/error bodies are
    # saved. Addresses are public research candidates, not recommendations.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(args.output.suffix + ".tmp")
    tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                              sort_keys=True, allow_nan=False)+"\n",
                   encoding="utf-8")
    tmp.replace(args.output)
    print(json.dumps({
        "rpc_request_count": result["rpc_request_count"],
        "rpc_error": result["rpc_error"],
        "group_summaries": {
            g: {
                "latest": x["latest_known_signature_utc"],
                "recent_signatures": x["recent_signatures_after_cutoff"],
                "outcome": x["outcome"],
                "interpreted": dict(Counter(
                    t["status"] for t in x["recent_transactions"])),
            } for g, x in result["wallet_groups"].items()
        },
        "shared_signatures": len(result["reused_signatures_across_groups"]),
        "realized_pnl": None,
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
