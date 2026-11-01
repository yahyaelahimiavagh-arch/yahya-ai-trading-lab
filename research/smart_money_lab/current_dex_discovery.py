"""One-shot public 24h Solana DEX wallet candidate discovery.

No API key, Solana/Helius RPC, external payments, orders or background jobs.
Uses GeckoTerminal's documented key-free public API; sample is recent trades
from a selected pool set, not all of Solana or the wallets' full histories.
Historical price/quantity are observations reported by the third-party indexer,
NOT verified wallet balances, execution or realized PnL.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

BASE = "https://api.geckoterminal.com/api/v2"
ACCEPT = "application/json;version=20230203"
MAX_REQUESTS = 21
MIN_REQUEST_INTERVAL = 7.0  # Conservative: docs conflict (~10 vs 30/min).
MAX_POOL_TRADES = 300  # Public endpoint: newest transactions only.
BASE58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
SIGNATURE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{80,90}$")
DAY = 86400


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def epoch(value) -> int | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None:
            return None
        return int(d.timestamp())
    except (ValueError, OverflowError):
        return None


def dec(value) -> Decimal | None:
    if value is None:
        return None
    try:
        value = Decimal(str(value))
        if value.is_finite() and value >= 0 and value < Decimal("1e15"):
            return value
    except (ValueError, InvalidOperation, TypeError):
        pass
    return None


def safe_number(value, default=0.0):
    d = dec(value)
    return float(d) if d is not None else default


def mint_from_relation(rels, name: str):
    if not isinstance(rels, dict):
        return None
    d = (rels.get(name) or {}).get("data")
    if not isinstance(d, dict):
        return None
    ident = d.get("id")
    if not isinstance(ident, str) or not ident.startswith("solana_"):
        return None
    mint = ident[len("solana_"):]
    return mint if BASE58.fullmatch(mint) else None


def extract_pool(item: dict, *, now: int) -> dict | None:
    if not isinstance(item, dict):
        return None
    a, rel = item.get("attributes"), item.get("relationships")
    if not isinstance(a, dict):
        return None
    address = a.get("address")
    base, quote = mint_from_relation(rel, "base_token"), mint_from_relation(rel, "quote_token")
    if not (isinstance(address, str) and BASE58.fullmatch(address)
            and base and quote and base != quote):
        return None
    liquidity = safe_number(a.get("reserve_in_usd"))
    volume = safe_number((a.get("volume_usd") or {}).get("h24"))
    transactions = (a.get("transactions") or {}).get("h24") or {}
    tx_count = (transactions.get("buys") or 0)+(transactions.get("sells") or 0)
    created = epoch(a.get("pool_created_at"))
    if (not 100000 <= liquidity <= 50000000 or volume < 25000
            or type(tx_count) is not int or tx_count < 10
            or created is None or created > now - 3*DAY):
        return None
    return {
        "pool": address,
        "base_mint": base,
        "quote_mint": quote,
        "pool_created_at": iso(created),
        "reported_liquidity_usd": round(liquidity, 2),
        "reported_volume_24h_usd": round(volume, 2),
        "reported_transactions_24h": tx_count,
        "pool_name": str(a.get("name") or "")[:90],
        "dex_id": str(((rel or {}).get("dex") or {}).get("data", {}).get("id") or "")[:80],
    }


def choose_pools(documents: list, *, now: int, limit: int = 16) -> list[dict]:
    if not 1 <= limit <= MAX_REQUESTS - len(documents):
        raise ValueError("invalid public pool cap")
    result = {}
    for doc in documents:
        if not isinstance(doc, dict):
            raise ValueError("provider pool result malformed")
        for row in doc.get("data", []):
            p = extract_pool(row, now=now)
            if p is not None:
                result[p["pool"]] = p
    # Prefer pools with enough volume to be meaningful, but few enough daily
    # transactions that a newest-300 sample may cover a substantial day.
    pools = sorted(result.values(), key=lambda p: (
        abs(math.log1p(p["reported_transactions_24h"]) - math.log1p(300)),
        -p["reported_liquidity_usd"], p["pool"]))
    selected, token_seen = [], set()
    for p in pools:
        if p["base_mint"] in token_seen:
            continue
        selected.append(p)
        token_seen.add(p["base_mint"])
        if len(selected) >= limit:
            break
    return selected


def normalize_trade(row: dict, pool: dict, *, now: int) -> tuple[dict | None, str | None]:
    if not isinstance(row, dict) or not isinstance(row.get("attributes"), dict):
        return None, "invalid_row"
    a = row["attributes"]
    if a.get("is_anomalous") is True:
        return None, "anomalous_indexer_trade"
    stamp = epoch(a.get("block_timestamp"))
    wallet = a.get("tx_from_address")
    sig = a.get("tx_hash")
    kind = a.get("kind")
    if (stamp is None or stamp < now - DAY or stamp > now + 120
            or not isinstance(wallet, str) or not BASE58.fullmatch(wallet)
            or not isinstance(sig, str) or not SIGNATURE.fullmatch(sig)):
        return None, "invalid_or_old_or_missing_identity"
    if kind == "buy":
        expected_from, expected_to = pool["quote_mint"], pool["base_mint"]
        quantity = a.get("to_token_amount")
    elif kind == "sell":
        expected_from, expected_to = pool["base_mint"], pool["quote_mint"]
        quantity = a.get("from_token_amount")
    else:
        return None, "unknown_side"
    if a.get("from_token_address") != expected_from or a.get("to_token_address") != expected_to:
        return None, "pool_mint_or_side_mismatch"
    qty, gross = dec(quantity), dec(a.get("volume_in_usd"))
    if qty is None or qty <= 0 or gross is None or gross < Decimal("0.01"):
        return None, "invalid_quantity_or_usd"
    return {
        "wallet": wallet,
        "tx_signature": sig,
        "pool": pool["pool"],
        "mint": pool["base_mint"],
        "side": kind,
        "timestamp": stamp,
        "quantity": str(qty),
        "volume_usd": str(gross),
        "source": "cached_public_dex_trade_snapshot",
    }, None


class PublicDexError(RuntimeError):
    def __init__(self, code):
        self.code = str(code)
        super().__init__("GeckoTerminal public API unavailable")


class PublicDex:
    def __init__(self):
        self.calls = 0
        self.last = None
        self.blocked = None

    def get(self, path: str):
        if (self.calls >= MAX_REQUESTS or self.blocked is not None):
            raise PublicDexError(self.blocked or "request_safety_cap")
        if not isinstance(path, str) or not (
            path in ("/networks/solana/trending_pools?page=1",
                     "/networks/solana/pools?page=1")
            or re.fullmatch(
                r"/networks/solana/pools/[1-9A-HJ-NP-Za-km-z]{32,44}/trades",
                path)
        ):
            raise ValueError("public endpoint outside read-only allowlist")
        if self.last is not None:
            wait = MIN_REQUEST_INTERVAL-(time.monotonic()-self.last)
            if wait > 0:
                time.sleep(wait)
        self.calls += 1
        self.last = time.monotonic()
        request = urllib.request.Request(BASE+path, headers={
            "Accept": ACCEPT, "User-Agent": "YATL-sml-readonly-research/1",
        })
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read(5_000_001)
        except urllib.error.HTTPError as e:
            self.blocked = f"http_{e.code}"
            raise PublicDexError(self.blocked) from None
        except (urllib.error.URLError, OSError):
            self.blocked = "network_unavailable"
            raise PublicDexError(self.blocked) from None
        if len(body) > 5_000_000:
            self.blocked = "oversized_reply"
            raise PublicDexError(self.blocked)
        try:
            doc = json.loads(body)
        except (UnicodeError, ValueError):
            self.blocked = "invalid_json"
            raise PublicDexError(self.blocked) from None
        if not isinstance(doc, dict) or not isinstance(doc.get("data"), list):
            self.blocked = "unexpected_schema"
            raise PublicDexError(self.blocked)
        return doc


def _fifo_indicative(events: list[dict]):
    """Match only observed buys followed by observed sells.

    This is NOT realized PnL. Unknown opening inventory, order splitting,
    pool gaps, transfer and actual fees can change it completely.
    """
    lots = defaultdict(deque)
    matched = Counter()
    amounts = defaultdict(Decimal)
    for e in sorted(events, key=lambda x: (x["timestamp"], x["tx_signature"], x["side"])):
        key = (e["wallet"], e["mint"])
        qty = Decimal(e["quantity"])
        usd = Decimal(e["volume_usd"])
        price = usd / qty
        if e["side"] == "buy":
            lots[key].append([qty, price])
            matched[(e["wallet"], "observed_buys")] += 1
        else:
            left = qty
            while left and lots[key]:
                lot = lots[key][0]
                piece = min(left, lot[0])
                amounts[(e["wallet"], "matched_spread_usd")] += piece*(price-lot[1])
                amounts[(e["wallet"], "matched_sell_quantity_units")] += piece
                left -= piece
                lot[0] -= piece
                if not lot[0]:
                    lots[key].popleft()
            if left:
                matched[(e["wallet"], "unmatched_sell_events")] += 1
            if left < qty:
                matched[(e["wallet"], "sell_events_with_observed_buy_basis")] += 1
    open_wallets = Counter()
    for (wallet, _), queue in lots.items():
        if sum((x[0] for x in queue), Decimal(0)) > 0:
            open_wallets[wallet] += 1
    return matched, amounts, open_wallets


def analyze(raw: list[dict], pools: list[dict], *, observed_at: int,
            rejected: dict | None = None, requests: int = 0,
            failed: str | None = None) -> dict:
    dedup = {}
    duplicate_rows = 0
    for e in raw:
        key = (e["wallet"], e["tx_signature"], e["mint"], e["side"],
               e["quantity"], e["volume_usd"])
        if key in dedup:
            duplicate_rows += 1
        else:
            dedup[key] = e
    events = list(dedup.values())
    hits = defaultdict(list)
    for e in events:
        hits[e["wallet"]].append(e)
    matched, amounts, open_wallets = _fifo_indicative(events)
    rows = []
    for wallet, trades in hits.items():
        buys = [t for t in trades if t["side"] == "buy"]
        sells = [t for t in trades if t["side"] == "sell"]
        pools_n = len({t["pool"] for t in trades})
        tokens_n = len({t["mint"] for t in trades})
        time_span = max(t["timestamp"] for t in trades)-min(t["timestamp"] for t in trades)
        known_sell = matched[(wallet, "sell_events_with_observed_buy_basis")]
        unbalanced = matched[(wallet, "unmatched_sell_events")]
        possible_automation = len(trades) > 80 or (
            len(trades) >= 12 and time_span < 120)
        if known_sell and tokens_n >= 2 and not possible_automation:
            status = "candidate_two_sided_multi_token_sample"
        elif known_sell:
            status = "observed_buy_and_later_sell_not_independent"
        else:
            status = "insufficient_two_sided_trade_evidence"
        rows.append({
            "wallet": wallet,
            "classification": status,
            "candidate_not_verified_skill": True,
            "total_sampled_trades": len(trades),
            "distinct_tokens": tokens_n,
            "distinct_pools": pools_n,
            "buy_trades": len(buys),
            "sell_trades": len(sells),
            "sell_events_with_observed_buy_basis": known_sell,
            "unmatched_sell_events": unbalanced,
            "open_lot_token_count_in_sample": open_wallets[wallet],
            "possible_high_frequency_automation": possible_automation,
            "observed_time_span_seconds": time_span,
            "sampled_first_utc": iso(min(t["timestamp"] for t in trades)),
            "sampled_last_utc": iso(max(t["timestamp"] for t in trades)),
            "indicative_fifo_gross_spread_usd_unverified": str(
                amounts[(wallet, "matched_spread_usd")].quantize(Decimal("0.0001"))),
        })
    rows.sort(key=lambda r: (
        -int(r["classification"] == "candidate_two_sided_multi_token_sample"),
        -r["distinct_tokens"],
        -r["sell_events_with_observed_buy_basis"],
        -r["total_sampled_trades"], r["wallet"]))
    return {
        "kind": "YATL_CURRENT_SOLANA_DEX_WALLET_DISCOVERY_V1",
        "data_retrieved_at_utc": iso(observed_at),
        "source": "GeckoTerminal key-free public API, 24h sampled pool trades",
        "api_requests": requests,
        "api_failure": failed,
        "pool_count": len(pools),
        "pools": pools,
        "total_normalized_pool_trade_rows": len(raw),
        "deduped_trades": len(events),
        "duplicate_trade_rows": duplicate_rows,
        "distinct_wallet_addresses": len(rows),
        "candidate_two_sided_multi_token_count": sum(
            r["classification"] == "candidate_two_sided_multi_token_sample" for r in rows),
        "wallets": rows,
        "excluded_trade_rows_by_reason": rejected or {},
        "limitations": [
            "Pool list sampled from trending/top pools; not representative of Solana.",
            "Trades endpoint returns newest up to 300 entries per pool, not all 24h.",
            "tx_from_address may be signer/router and is not proof of controlling owner.",
            "Indexer estimates USD volume; no independent SOL transaction receipt verification.",
            "Opening holdings, transfers and off-pool trading are unobserved.",
            "Matched FIFO is partial within sampled observations, gross and before fees.",
            "No wallet is a validated profitable trader or viable follower.",
        ],
        "no_helius_calls": True,
        "no_real_orders": True,
    }


def run(provider, *, observed_at: int, max_pools: int = 16) -> tuple[dict, list[dict]]:
    if type(observed_at) is not int or observed_at < 1780000000:
        raise ValueError("invalid observation timestamp")
    documents = []
    err = None
    for path in ("/networks/solana/trending_pools?page=1",
                 "/networks/solana/pools?page=1"):
        try:
            documents.append(provider.get(path))
        except PublicDexError as ex:
            err = ex.code
            break
    if not documents:
        return analyze([], [], observed_at=observed_at, requests=provider.calls,
                       failed=err), []
    pools = choose_pools(documents, now=observed_at, limit=max_pools)
    rejected = Counter()
    raw = []
    seen_pools = []
    for p in pools:
        try:
            doc = provider.get(f"/networks/solana/pools/{p['pool']}/trades")
        except PublicDexError as ex:
            err = ex.code
            break
        entries = doc["data"][:MAX_POOL_TRADES]
        p = {**p, "trades_returned": len(entries)}
        pool_times = []
        for item in entries:
            trade, reason = normalize_trade(item, p, now=observed_at)
            if reason:
                rejected[reason] += 1
            else:
                raw.append(trade)
                pool_times.append(trade["timestamp"])
        p["oldest_accepted_trade_utc"] = iso(min(pool_times)) if pool_times else None
        p["newest_accepted_trade_utc"] = iso(max(pool_times)) if pool_times else None
        p["sample_fills_reported_24h"] = (
            len(entries) < MAX_POOL_TRADES and
            (p["reported_transactions_24h"] <= MAX_POOL_TRADES))
        seen_pools.append(p)
    return analyze(raw, seen_pools, observed_at=observed_at,
                   rejected=dict(rejected), requests=provider.calls, failed=err), raw


def save(result: dict, records: list[dict], folder: Path) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    outputs = {
        "wallet_candidates.json": json.dumps(result, ensure_ascii=False, indent=2,
                                               allow_nan=False),
        "wallet_candidates.csv": None,
        "normalized_trades.jsonl": "\n".join(
            json.dumps(t, sort_keys=True, separators=(",", ":")) for t in records)+"\n",
    }
    for name, content in outputs.items():
        path = folder / name
        tmp = folder / (name + ".tmp")
        if name.endswith(".csv"):
            cols = (list(result["wallets"][0]) if result["wallets"] else
                    ["wallet","classification","total_sampled_trades","distinct_tokens"])
            with tmp.open("w", newline="", encoding="utf-8") as f:
                wr = csv.DictWriter(f, fieldnames=cols)
                wr.writeheader()
                wr.writerows(result["wallets"])
        else:
            tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    manifest = {}
    for name in outputs:
        path = folder/name
        with path.open("rb") as f:
            manifest[name] = hashlib.file_digest(f, "sha256").hexdigest()
    (folder/"sha256_manifest.json").write_text(
        json.dumps(manifest, indent=2)+"\n", encoding="utf-8")


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--max-pools", type=int, default=16)
    args = p.parse_args(argv)
    provider = PublicDex()
    result, records = run(provider, observed_at=int(time.time()), max_pools=args.max_pools)
    save(result, records, args.output_dir)
    print(json.dumps({
        "as_of": result["data_retrieved_at_utc"],
        "requests": result["api_requests"], "provider_error": result["api_failure"],
        "pools": result["pool_count"], "trades": result["deduped_trades"],
        "wallets": result["distinct_wallet_addresses"],
        "two_sided_multi_token_candidates": result["candidate_two_sided_multi_token_count"],
        "top_research_candidates": [
            {key: w[key] for key in (
                "wallet","distinct_tokens","total_sampled_trades",
                "sell_events_with_observed_buy_basis",
                "indicative_fifo_gross_spread_usd_unverified",
                "classification")}
            for w in result["wallets"][:12]
        ],
        "no_verified_trader_pnl": True, "helius_requests": 0,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
