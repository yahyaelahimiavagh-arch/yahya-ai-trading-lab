"""Offline audit of observed Solana position holding time and delayed print coverage.

Source: exact immutable ZIP artifact from 2026-11-01 PR #193.
NO network, RPC, Helius, live orders or trading keys.

A last observed DEX indexer trade print is NOT an executable DEX quote.
FIFO matches are partial known-basis observations, NOT realized PnL.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict, deque
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from statistics import median
import zipfile

REQUIRED=("wallet_candidates.json","normalized_trades.jsonl","sha256_manifest.json")
MAX_MEMBER_SIZE=15_000_000
DELAY_SCENARIOS=(117,180,300)
PRINT_AGES=(30,120)


def _positive(x):
    try:
        d=Decimal(str(x))
    except (ValueError, TypeError, InvalidOperation):
        raise ValueError("invalid trade decimal") from None
    if not d.is_finite() or not 0<d<Decimal("1e15"):
        raise ValueError("non-positive or infinite trade value")
    return d


def read_snapshot(zip_path: Path):
    with zipfile.ZipFile(zip_path) as source:
        if any(source.getinfo(k).file_size>MAX_MEMBER_SIZE for k in REQUIRED):
            raise ValueError("oversized public snapshot")
        files={k:source.read(k) for k in REQUIRED}
    manifest=json.loads(files["sha256_manifest.json"])
    for name in REQUIRED[:2]:
        if hashlib.sha256(files[name]).hexdigest()!=manifest.get(name):
            raise ValueError("public snapshot source SHA-256 mismatch")
    summary=json.loads(files["wallet_candidates.json"])
    if summary.get("kind")!="YATL_CURRENT_SOLANA_DEX_WALLET_DISCOVERY_V1":
        raise ValueError("incorrect source snapshot kind")
    events=[]
    for line in files["normalized_trades.jsonl"].splitlines():
        r=json.loads(line)
        for key in ("wallet","tx_signature","pool","mint","side","quantity",
                    "volume_usd","timestamp"):
            if key not in r:
                raise ValueError("invalid public trade schema")
        if (r["side"] not in ("buy","sell")
                or type(r["timestamp"]) is not int
                or not all(isinstance(r[k],str) and r[k] for k in
                           ("wallet","tx_signature","pool","mint"))):
            raise ValueError("invalid trade identity, timestamp or side")
        events.append({**r,"qty":_positive(r["quantity"]),
                       "usd":_positive(r["volume_usd"])})
    return summary,events


def reconstruct(events: list[dict]):
    """Match observed buy lots with strictly later sell timestamps.

    A single economically related sale can consume many lots. The resulting
    fragments must NOT be treated as statistically independent closed trades.
    """
    by_key={}
    duplicates=0
    for e in events:
        key=(e["wallet"],e["mint"],e["pool"],e["side"],
             e["tx_signature"],e["timestamp"])
        if key in by_key:
            by_key[key]["qty"]+=e["qty"]
            by_key[key]["usd"]+=e["usd"]
            duplicates+=1
        else:
            by_key[key]={**e}
    ordered=sorted(by_key.values(),key=lambda e:(
        e["timestamp"],0 if e["side"]=="sell" else 1,
        e["tx_signature"],e["wallet"]))
    fifo=defaultdict(deque)
    unmatched=Counter()
    matches=[]
    for e in ordered:
        pair=(e["wallet"],e["mint"])
        px=e["usd"]/e["qty"]
        if e["side"]=="buy":
            fifo[pair].append({"qty":e["qty"],"price":px,
                               "time":e["timestamp"],"sig":e["tx_signature"],
                               "pool":e["pool"]})
            continue
        remaining=e["qty"]
        while remaining>0 and fifo[pair]:
            lot=fifo[pair][0]
            # Same-second sequence is not known from coarse timestamps.
            if lot["time"]>=e["timestamp"]:
                break
            chunk=min(lot["qty"],remaining)
            matches.append({
                "wallet":e["wallet"],"mint":e["mint"],
                "buy_sig":lot["sig"],"sell_sig":e["tx_signature"],
                "buy_pool":lot["pool"],"sell_pool":e["pool"],
                "buy_time":lot["time"],"sell_time":e["timestamp"],
                "hold_seconds":e["timestamp"]-lot["time"],
                "qty":chunk,
                "source_gross_spread_usd":chunk*(px-lot["price"]),
            })
            remaining-=chunk
            lot["qty"]-=chunk
            if lot["qty"]==0:
                fifo[pair].popleft()
        if remaining>0:
            unmatched[e["wallet"]]+=1
    return matches,{
        "merged_transaction_side_rows":len(by_key),
        "merged_same_signature_rows":duplicates,
        "unmatched_sell_events":sum(unmatched.values()),
        "unmatched_sell_wallets":len(unmatched),
    }


def print_index(events):
    by_pool=defaultdict(list)
    for e in events:
        by_pool[e["pool"]].append((e["timestamp"],e["usd"]/e["qty"]))
    index={}
    for pool,rows in by_pool.items():
        rows.sort(key=lambda x:x[0])
        index[pool]=([t for t,_ in rows],rows)
    return index


def asof_print(index,pool,decision,age_limit):
    """Never read a trade printed AFTER the simulated decision timestamp."""
    values=index.get(pool)
    if values is None:
        return None
    timestamps,rows=values
    i=bisect_right(timestamps,decision)-1
    if i<0:
        return None
    timestamp,px=rows[i]
    if timestamp>decision or decision-timestamp>age_limit:
        return None
    return px


def evaluate(matches,index,*,delay,age_limit):
    if (type(delay) is not int or type(age_limit) is not int or
            delay<0 or age_limit<0):
        raise ValueError("negative or non-integer timing threshold")
    counts=Counter()
    covered=[]
    per_wallet=defaultdict(Counter)
    for m in matches:
        if m["hold_seconds"]<=delay:
            status="leader_exited_before_copy_entry"
        else:
            buy_px=asof_print(index,m["buy_pool"],m["buy_time"]+delay,age_limit)
            sell_px=asof_print(index,m["sell_pool"],m["sell_time"]+delay,age_limit)
            if buy_px is None and sell_px is None:
                status="both_asof_prints_missing"
            elif buy_px is None:
                status="entry_asof_print_missing"
            elif sell_px is None:
                status="exit_asof_print_missing"
            else:
                status="both_asof_prints_present"
                covered.append({**m,"buy_asof_print":buy_px,
                                "sell_asof_print":sell_px,
                                "gross_return_pct":(sell_px/buy_px-1)*100})
        counts[status]+=1
        per_wallet[m["wallet"]][status]+=1
    return counts,covered,per_wallet


def _median_pct(covered,cost_bps):
    if not covered:
        return None
    half=Decimal(cost_bps)/20000
    return round(float(median([
        ((r["sell_asof_print"]*(1-half)) /
         (r["buy_asof_print"]*(1+half))-1)*100 for r in covered
    ])),4)


def analyze(summary,events):
    matches,unmatched=reconstruct(events)
    index=print_index(events)
    scenarios={}
    checks={}
    for delay in DELAY_SCENARIOS:
        for age in PRINT_AGES:
            key=f"{delay}s_delay_{age}s_max_print_age"
            counts,covered,by_wallet=evaluate(matches,index,delay=delay,
                                               age_limit=age)
            checks[key]=(counts,covered,by_wallet)
            scenarios[key]={
                "fifo_fragments":len(matches),
                "classifications":dict(counts),
                "covered_asof_print_fragments":len(covered),
                "covered_fraction_pct":round(100*len(covered)/len(matches),2)
                                        if matches else None,
                "covered_distinct_wallets":len({r["wallet"] for r in covered}),
                "covered_distinct_tokens":len({r["mint"] for r in covered}),
                "covered_fragments_positive_gross":sum(
                    r["gross_return_pct"]>0 for r in covered),
                "median_gross_return_pct_not_executable":_median_pct(covered,0),
                "hypothetical_median_after_total_round_trip_cost_bps":{
                    str(bps):_median_pct(covered,bps) for bps in (0,150,300)
                },
            }
    _,covered_117,by_wallet=checks["117s_delay_30s_max_print_age"]
    top=[]
    for w in summary.get("wallets",[]):
        if w.get("classification")!="candidate_two_sided_multi_token_sample":
            continue
        wallet=w["wallet"]
        mine=[x for x in matches if x["wallet"]==wallet]
        sampled=[x for x in covered_117 if x["wallet"]==wallet]
        top.append({
            "wallet":wallet,
            "tokens_with_observed_matching":len({x["mint"] for x in mine}),
            "matched_fifo_fragments":len(mine),
            "unique_matched_buy_signatures":len({x["buy_sig"] for x in mine}),
            "unique_matched_sell_signatures":len({x["sell_sig"] for x in mine}),
            "median_holding_seconds":round(median(x["hold_seconds"] for x in mine))
                                     if mine else None,
            "fragments_holding_more_than_117s":sum(x["hold_seconds"]>117 for x in mine),
            "fragments_holding_more_than_180s":sum(x["hold_seconds"]>180 for x in mine),
            "fragments_holding_more_than_900s":sum(x["hold_seconds"]>900 for x in mine),
            "sampled_source_gross_spread_usd":str(sum(
                (x["source_gross_spread_usd"] for x in mine),
                Decimal(0)).quantize(Decimal("0.0001"))),
            "fragments_with_117s_30s_asof_prints":len(sampled),
            "conditional_median_gross_print_return_pct":_median_pct(sampled,0),
            "follower_print_status_counts":dict(by_wallet[wallet]),
            "not_proven_profitable":True,
        })
    return {
        "kind":"YATL_OFFLINE_HOLD_LATENCY_AUDIT_V1",
        "source_snapshot_utc":summary["data_retrieved_at_utc"],
        "source_api_failure":summary.get("api_failure"),
        "source_pools":summary.get("pool_count"),
        "source_wallet_count":summary.get("distinct_wallet_addresses"),
        "source_trade_rows":len(events),
        "matching_quality":{
            **unmatched,
            "fifo_matched_fragments":len(matches),
            "unique_buy_signatures_with_matched_sale":
                len({x["buy_sig"] for x in matches}),
            "unique_sell_signatures_with_matched_buy":
                len({x["sell_sig"] for x in matches}),
            "matched_wallet_count":len({x["wallet"] for x in matches}),
            "matched_distinct_tokens":len({x["mint"] for x in matches}),
            "median_fragment_holding_seconds":round(
                median(x["hold_seconds"] for x in matches)) if matches else None,
        },
        "scenarios":scenarios,
        "selected_top_10":top,
        "limitations":[
            "Only the newest 300 trades per pool from four selected trending pools; incomplete historical inventory.",
            "FIFO fragments from the same wallet/token are correlated and must NOT be counted as independent trials.",
            "The public indexer's price print is not a firm executable route quote nor proven available at decision time.",
            "No future trade price print is used for simulated historical as-of price lookup.",
            "No validation of token transfer history, other pools, signed order routing, MEV, real slippage, or fees.",
            "150/300 bps are hypothetical ALL-IN round-trip costs, not measured provider pricing.",
            "This is a selective hindsight study of known wallet buy/sell events; cannot establish positive expected returns.",
            "No provider API requests or trading operations are performed.",
        ],
        "no_api_calls":True,"realized_pnl":None,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args(argv)
    summary,events=read_snapshot(args.source_zip)
    outcome=analyze(summary,events)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(outcome,ensure_ascii=False,indent=2,
                                      sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "matching_quality":outcome["matching_quality"],
        "117s_30s":outcome["scenarios"]["117s_delay_30s_max_print_age"],
        "selected_wallet_count":len(outcome["selected_top_10"]),
        "output":str(args.output),
        "realized_pnl":None,
    },ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
