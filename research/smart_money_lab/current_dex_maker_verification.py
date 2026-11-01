"""Verify the ten PUBLIC DEX indexer maker/signature pairs against Solana.

One bounded finalized getTransaction per frozen sample via official public RPC.
The indexer's maker address can be a routing signer, not an economic trader.
No API keys, Helius requests, trading orders or account access.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path

from .recent_wallet_receipts import (
    BASE58, SIGNATURE58, PublicRpc, PublicRpcError, interpret_transaction, utc,
)
from .group_chain_fingerprints import fingerprint

MAX_SIGNATURES = 10
MAX_TIMESTAMP_SKEW_SECONDS = 120


def audit(source: dict, rpc) -> dict:
    samples = source.get("samples")
    if not isinstance(samples, list) or not 1 <= len(samples) <= MAX_SIGNATURES:
        raise ValueError("expected a bounded public candidate sample")
    evidence = []
    seen_signatures = set()
    error = None
    for entry in samples:
        wallet, sig, rank, kind, ts = (
            entry.get("wallet"),entry.get("signature"),entry.get("rank"),
            entry.get("kind"),entry.get("reported_timestamp"))
        if (not isinstance(wallet,str) or not BASE58.fullmatch(wallet)
                or not isinstance(sig,str) or not SIGNATURE58.fullmatch(sig)
                or sig in seen_signatures or type(rank) is not int
                or kind not in ("buy","sell") or type(ts) is not int):
            raise ValueError("invalid or duplicated public sample")
        seen_signatures.add(sig)
        result = {
            "wallet": wallet, "rank_in_public_sample":rank,
            "market_indexer_kind":kind,
            "market_indexer_timestamp":utc(ts),
            "onchain_status":"not_checked",
            "onchain_wallet_is_signer": None,
            "onchain_wallet_is_fee_payer": None,
            "fee_payer":None,
            "onchain_timestamp":None,
            "time_disagreement_seconds":None,
            "top_level_programs":[],
            "owned_token_change_classification":None,
            "owned_token_change_count":None,
            "warning": "No profitability inference from one sampled transaction",
        }
        evidence.append(result)
        if error:
            result["onchain_status"] = "not_checked_rpc_unavailable"
            continue
        try:
            tx = rpc.transaction(sig)
        except PublicRpcError as exc:
            error = exc.code
            result["onchain_status"] = "rpc_unavailable"
            continue
        fp = fingerprint(tx, wallet, sig)
        result["onchain_status"] = fp["status"]
        result["onchain_wallet_is_signer"] = fp["wallet_is_signer"]
        result["onchain_wallet_is_fee_payer"] = fp["wallet_is_fee_payer"]
        result["fee_payer"] = fp["fee_payer"]
        result["onchain_timestamp"] = fp["block_time_utc"]
        result["top_level_programs"] = fp["top_level_programs"]
        if isinstance(tx, dict):
            chain_time = tx.get("blockTime")
            if type(chain_time) is int:
                result["time_disagreement_seconds"] = abs(chain_time - ts)
                if result["time_disagreement_seconds"] > MAX_TIMESTAMP_SKEW_SECONDS:
                    result["onchain_status"] = "market_chain_time_mismatch"
            interpretation = interpret_transaction(tx,wallet,sig)
            result["owned_token_change_classification"] = interpretation["status"]
            result["owned_token_change_count"] = len(
                interpretation.get("owner_token_deltas") or {})
        if result["onchain_wallet_is_signer"] is False:
            result["onchain_status"] = "indexer_maker_not_onchain_signer"
    payers = defaultdict(list)
    for x in evidence:
        if x["fee_payer"]:
            payers[x["fee_payer"]].append(x["wallet"])
    return {
        "kind":"YATL_PUBLIC_DEX_MAKER_ONCHAIN_VERIFICATION_V1",
        "source_snapshot":source.get("snapshot"),
        "input_sample_count":len(samples),
        "rpc_requests":rpc.requests,
        "rpc_error":error,
        "onchain_signer_yes":sum(x["onchain_wallet_is_signer"] is True for x in evidence),
        "onchain_signer_no":sum(x["onchain_wallet_is_signer"] is False for x in evidence),
        "unknown_signer":sum(x["onchain_wallet_is_signer"] is None for x in evidence),
        "shared_fee_payers":{
            payer: wallets for payer,wallets in payers.items() if len(wallets)>1
        },
        "classifications":dict(Counter(x["onchain_status"] for x in evidence)),
        "evidence":evidence,
        "no_verified_profit_or_copyability":True,
        "helius_calls":0,
        "warning":(
            "A public onchain signature verifies only an authorization on one "
            "transaction. Matching a DEX indexer maker to a signer does NOT "
            "establish that the person controls the wallet, that the full swap "
            "was owned by it, or that follower copy trading is profitable."
        ),
    }


def main(argv=None):
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args(argv)
    data=json.loads(args.input.read_text(encoding="utf-8"))
    result=audit(data,PublicRpc())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    tmp=args.output.with_suffix(args.output.suffix+".tmp")
    tmp.write_text(json.dumps(result,indent=2,ensure_ascii=False,
                              sort_keys=True)+"\n",encoding="utf-8")
    tmp.replace(args.output)
    print(json.dumps({
        "rpc_requests":result["rpc_requests"],
        "rpc_error":result["rpc_error"],
        "input":result["input_sample_count"],
        "signers_yes":result["onchain_signer_yes"],
        "signers_no":result["onchain_signer_no"],
        "unknown_signers":result["unknown_signer"],
        "shared_fee_payer_group_sizes":[len(v) for v in
                                         result["shared_fee_payers"].values()],
        "classifications":result["classifications"],
        "sample": [{
            "wallet":x["wallet"],
            "signer":x["onchain_wallet_is_signer"],
            "fee_payer":x["fee_payer"],
            "status":x["onchain_status"],
            "owner_token_changes":x["owned_token_change_count"],
        } for x in result["evidence"]],
    },indent=2,ensure_ascii=False))


if __name__=="__main__":
    main()
