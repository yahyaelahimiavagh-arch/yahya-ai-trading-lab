"""Bounded public-chain forensic fingerprints for selected historical wallets.

Checks signer status, fee-payer, native lamport changes and instruction programs.
These are OBSERVATIONS, NOT proof of shared ownership, copyability or profit.
"""
from __future__ import annotations
from collections import defaultdict, Counter
import json
from pathlib import Path

from .recent_wallet_receipts import PublicRpc, PublicRpcError, utc, WALLETS

SELECTED = {
    "group1_rank1": WALLETS["behavior_group_1"],
    "group1_rank2": "8iehXxodAVfs1LQ3DHu2Ss5RK5ZtWKat9aTqzsMorjF6",
    "group1_rank3": "DqJ2k8FAELhyBv21dQbaYbiuFahoWHL82vK21vhmkTKn",
    "group1_rank4": "GetzpN6Yz5zvNDdU5rMCa9Sh6nbQbUy82SofChfwNgBr",
    "group2_rank10": WALLETS["behavior_group_2"],
    "group3_rank20": WALLETS["behavior_group_3"],
}
MAX_WALLETS = 6


def _account_pubkey(row):
    if isinstance(row, str):
        return row
    return row.get("pubkey") if isinstance(row, dict) else None


def fingerprint(tx, wallet: str, signature: str) -> dict:
    result = {
        "signature": signature,
        "block_time_utc": utc(tx.get("blockTime")) if isinstance(tx, dict) else None,
        "slot": tx.get("slot") if isinstance(tx, dict) else None,
        "status": "unavailable",
        "wallet_listed": False,
        "wallet_is_signer": False,
        "wallet_is_fee_payer": False,
        "fee_payer": None,
        "wallet_native_lamports_change": None,
        "network_fee_lamports": None,
        "top_level_programs": [],
        "top_level_instruction_types": [],
    }
    if not isinstance(tx, dict):
        return result
    meta = tx.get("meta")
    message = (tx.get("transaction") or {}).get("message")
    if not isinstance(meta, dict) or not isinstance(message, dict):
        result["status"] = "invalid_transaction_metadata"
        return result
    keys = message.get("accountKeys")
    if not isinstance(keys, list) or not keys:
        result["status"] = "missing_account_keys"
        return result
    addresses = [_account_pubkey(row) for row in keys]
    result["wallet_listed"] = wallet in addresses
    result["fee_payer"] = addresses[0]
    result["wallet_is_fee_payer"] = addresses[0] == wallet
    result["wallet_is_signer"] = any(
        isinstance(row, dict) and row.get("signer") is True and
        row.get("pubkey") == wallet for row in keys)
    result["network_fee_lamports"] = (
        meta.get("fee") if type(meta.get("fee")) is int else None)
    pre, post = meta.get("preBalances"), meta.get("postBalances")
    if (wallet in addresses and isinstance(pre, list) and
            isinstance(post, list) and len(pre) == len(keys) and len(post) == len(keys)):
        ix = addresses.index(wallet)
        if type(pre[ix]) is int and type(post[ix]) is int:
            result["wallet_native_lamports_change"] = post[ix] - pre[ix]
    programs = set()
    kinds = set()
    for ins in message.get("instructions") or []:
        if not isinstance(ins, dict):
            continue
        program = ins.get("programId") or ins.get("program")
        if isinstance(program, str) and program:
            programs.add(program)
        parsed = ins.get("parsed")
        if isinstance(parsed, dict) and isinstance(parsed.get("type"), str):
            kinds.add(parsed["type"])
    result["top_level_programs"] = sorted(programs)
    result["top_level_instruction_types"] = sorted(kinds)
    result["status"] = "failed_onchain" if meta.get("err") is not None else "confirmed_finalized"
    return result


def audit(wallets: dict, rpc) -> dict:
    if len(wallets) > MAX_WALLETS:
        raise ValueError("forensic fingerprint cap exceeded")
    rows = {}
    cache = {}
    code = None
    signature_groups = defaultdict(set)
    for label, wallet in wallets.items():
        if code:
            rows[label] = {"wallet": wallet, "status": "not_checked_rpc_unavailable"}
            continue
        try:
            signatures = rpc.signatures(wallet)
            if not signatures or not isinstance(signatures[0], dict):
                rows[label] = {"wallet": wallet, "status": "no_recent_signature"}
                continue
            sig = signatures[0].get("signature")
            signature_groups[sig].add(label)
            if sig not in cache:
                cache[sig] = rpc.transaction(sig)
            rows[label] = {
                "wallet": wallet,
                **fingerprint(cache[sig], wallet, sig),
            }
        except PublicRpcError as exc:
            code = exc.code
            rows[label] = {"wallet": wallet, "status": "rpc_unavailable"}
    payer_groups = defaultdict(set)
    for label, item in rows.items():
        payer = item.get("fee_payer")
        if isinstance(payer, str):
            payer_groups[payer].add(label)
    return {
        "kind": "YATL_SOLANA_GROUP_FINGERPRINTS_V1",
        "wallets": rows,
        "rpc_request_count": rpc.requests,
        "rpc_error": code,
        "shared_latest_signatures": [
            {"signature": sig, "wallet_labels": sorted(labels)}
            for sig, labels in signature_groups.items() if len(labels) > 1],
        "shared_fee_payers": [
            {"fee_payer": payer, "wallet_labels": sorted(labels)}
            for payer, labels in payer_groups.items() if len(labels) > 1],
        "warning": ("Same timestamps, program IDs or fee payer can suggest links "
                    "but cannot alone prove shared ownership, coordinated trading "
                    "or profitable copyability. On-chain native balance changes "
                    "include transfers, rent and fees; they are NOT trade PnL."),
        "realized_pnl": None,
        "helius_requests": 0,
    }


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args(argv)
    result = audit(SELECTED, PublicRpc())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(args.output.suffix+".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False,
                              indent=2, sort_keys=True)+"\n", encoding="utf-8")
    tmp.replace(args.output)
    print(json.dumps({
        "rpc_request_count": result["rpc_request_count"],
        "rpc_error": result["rpc_error"],
        "shared_signatures": len(result["shared_latest_signatures"]),
        "shared_fee_payers": len(result["shared_fee_payers"]),
        "wallet_snapshots": {
            label: {
                "block_time_utc": info.get("block_time_utc"),
                "signer": info.get("wallet_is_signer"),
                "fee_payer": info.get("wallet_is_fee_payer"),
                "native_change_lamports": info.get("wallet_native_lamports_change"),
                "programs": info.get("top_level_programs"),
                "instruction_types": info.get("top_level_instruction_types"),
            } for label, info in result["wallets"].items()},
        "pnl": None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
