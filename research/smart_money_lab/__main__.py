"""Command line runner: discover -> screen -> 24h paper observe -> report.

No private key, sendTransaction, swap execution or broker integration exists.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path
from decimal import Decimal

from .engine import PaperLab, Trade, Holding, dec, score_wallet, rank_wallets, DELAYS
from .providers import Helius, Market, SOL, discover_candidates, get_json, parse_swap, valid_address


def write_json(path: Path, payload: dict | list):
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(path.suffix + ".tmp")
    staging.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    staging.replace(path)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sol_candles(days: int, end: int) -> dict[int, Decimal]:
    """Public hour candles; use PREVIOUS closed candle to avoid future leakage.

    If data is unavailable, SOL trades remain unscored (not assumed profitable).
    """
    begin = end - (days + 2) * 86400
    result = {}
    cursor = begin * 1000
    stop = end * 1000
    for _ in range((days + 2) * 24 // 1000 + 2):
        params = urllib.parse.urlencode({
            "symbol": "SOLUSDT", "interval": "1h", "startTime": cursor,
            "endTime": stop, "limit": 1000,
        })
        payload = get_json("https://api.binance.com/api/v3/klines?" + params)
        if not isinstance(payload, list):
            raise ValueError("unexpected candle response")
        if not payload:
            break
        for candle in payload:
            if isinstance(candle, list) and len(candle) > 6:
                # close time is when estimate becomes available
                result[int(candle[6]) // 1000 // 3600] = dec(candle[4])
        next_cursor = int(payload[-1][0]) + 3600000
        if next_cursor <= cursor:
            raise ValueError("repeated candle cursor")
        cursor = next_cursor
        if cursor >= stop:
            break
    return result


def parse_history(raw: list[dict], wallet: str, now: int, prices: dict[int, Decimal]):
    trades = []
    swaps = 0
    missed = 0
    for tx in raw:
        if tx.get("type") != "SWAP" or tx.get("feePayer") != wallet:
            continue
        swaps += 1
        hour = int(tx.get("timestamp", 0)) // 3600 - 1
        t = parse_swap(tx, wallet=wallet, observed_at=now,
                       historical_sol_usd=prices.get(hour))
        if t is None:
            missed += 1
        else:
            trades.append(t)
    return trades, swaps, missed


def screen(args):
    helius = Helius(os.getenv("HELIUS_API_KEY", ""))
    market = Market()
    candidates = read_json(Path(args.candidates))
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a JSON array")
    addresses = []
    for row in candidates:
        wallet = row.get("wallet") if isinstance(row, dict) else row
        if wallet not in addresses:
            addresses.append(valid_address(wallet))
    addresses = addresses[:args.max_wallets]
    now = int(time.time())
    try:
        prices = sol_candles(args.days, now)
    except (RuntimeError, ValueError):
        prices = {}  # fail closed for SOL historical scoring
    scored = []
    for wallet in addresses:
        try:
            raw, complete = helius.history(
                wallet, earliest_ts=now - args.days * 86400, max_pages=args.max_pages)
            parsed, swaps, skipped = parse_history(raw, wallet, now, prices)
            historical = [t for t in parsed if t.chain_time >= now - args.days * 86400]
            result = score_wallet(wallet, historical, cutoff=now, min_closed=50, min_days=15)
            result["history_complete"] = complete
            result["total_swaps_observed"] = swaps
            result["unparsed_swaps"] = skipped
            # Require at least 80% swaps parsed to avoid biased ROI estimates.
            quality = swaps > 0 and (swaps - skipped) / swaps >= 0.8
            recent_mints = list(dict.fromkeys(t.mint for t in sorted(
                historical, key=lambda x: x.chain_time, reverse=True)))[:10]
            liquidity = []
            for mint in recent_mints:
                try:
                    q = market.token(mint, now=now)
                except (RuntimeError, ValueError):
                    q = None
                if q:
                    liquidity.append(dec(q["liquidity_usd"]))
            copyable = len(liquidity) >= 3 and min(liquidity) >= Decimal("20000")
            result["min_liquidity_usd"] = str(min(liquidity, default=Decimal("0")))
            result["copyable"] = bool(copyable and quality)
            result["copyability_score"] = str(min(25, len(liquidity) * 2.5)) if copyable else "0"
            result["eligible"] = bool(
                complete and quality and result["meets_activity_thresholds"] and copyable
            )
        except (RuntimeError, ValueError) as exc:
            result = {"wallet": wallet, "eligible": False,
                      "error": str(exc)[:120], "history_complete": False}
        scored.append(result)
        write_json(Path(args.output), scored)
    blind, smart = rank_wallets(scored)
    print(json.dumps({"screened": len(scored), "eligible": len(smart),
                      "blind": len(blind), "smart": len(smart),
                      "output": args.output}))


def trade_data(t: Trade) -> dict:
    return {**vars(t), "amount": str(t.amount), "usd_notional": str(t.usd_notional)}


def restore_trade(data: dict) -> Trade:
    return Trade(**{**data, "amount": dec(data["amount"]),
                    "usd_notional": dec(data["usd_notional"])})


def snapshot(lab: PaperLab, quotes: dict, now: int, polls: int, skips: dict):
    return {
        "start_at": lab.start_at, "blind": sorted(lab.blind), "smart": sorted(lab.smart),
        "seen": sorted(lab.seen), "polls": polls, "skips": skips, "quotes": quotes,
        "pending": [{"due": due, "portfolio": pid, "trade": trade_data(t), "owner": owner}
                    for due, pid, t, owner in lab.pending],
        "votes": {k: [trade_data(x) for x in v] for k, v in lab.vote_log.items()},
        "portfolios": {
            pid: {"cash": str(p.cash), "peak_equity": str(p.peak_equity),
                  "halted": p.halted, "fills": p.fills, "rejected": p.rejected,
                  "holdings": {k: {"wallet": h.wallet, "mint": h.mint,
                                  "qty": str(h.qty), "cost": str(h.cost)}
                               for k, h in p.holdings.items()}}
            for pid, p in lab.portfolios.items()
        },
    }


def restore(doc: dict) -> PaperLab:
    lab = PaperLab(int(doc["start_at"]), list(doc["blind"]), list(doc["smart"]))
    lab.seen = set(doc["seen"])
    lab.pending = [(int(x["due"]), x["portfolio"], restore_trade(x["trade"]),
                    x["owner"]) for x in doc["pending"]]
    for k, rows in doc.get("votes", {}).items():
        lab.vote_log[k] = [restore_trade(x) for x in rows]
    for pid, pdoc in doc["portfolios"].items():
        p = lab.portfolios[pid]
        p.cash = dec(pdoc["cash"])
        p.peak_equity = dec(pdoc["peak_equity"])
        p.halted = bool(pdoc["halted"])
        p.fills = pdoc["fills"]
        p.rejected = pdoc["rejected"]
        p.holdings = {k: Holding(h["wallet"], h["mint"], dec(h["qty"]), dec(h["cost"]))
                      for k, h in pdoc["holdings"].items()}
    return lab


def observe(args):
    helius = Helius(os.getenv("HELIUS_API_KEY", ""))
    market = Market()
    path = Path(args.state)
    if path.exists():
        if not args.resume:
            raise ValueError("state file already exists; use --resume or a new path")
        saved = read_json(path)
        lab = restore(saved)
        quotes = saved.get("quotes", {})
        polls, skips = saved.get("polls", 0), saved.get("skips", {})
    else:
        screened = read_json(Path(args.screened))
        if not isinstance(screened, list):
            raise ValueError("screened file must contain wallet records")
        blind, smart = rank_wallets(screened)
        if len(smart) < 2:
            raise ValueError("need >=2 independently screened eligible wallets; no bypass")
        lab = PaperLab(int(time.time()), blind, smart)
        quotes, polls, skips = {}, 0, {}
        write_json(path, snapshot(lab, quotes, lab.start_at, polls, skips))
    finish = lab.start_at + args.hours * 3600
    if time.time() >= finish:
        raise ValueError("observation window already complete")
    next_poll = 0
    last_observed = 0
    # No infinite web scraping: 24h max, <=15 wallets, >=15s poll.
    while int(time.time()) < finish:
        now = int(time.time())
        if now >= next_poll:
            new_mints = set()
            try:
                sol_price = market.sol_usd(now=now)
            except (RuntimeError, ValueError):
                sol_price = None
                skips["sol_quote_unavailable"] = skips.get("sol_quote_unavailable", 0) + 1
            for wallet in sorted(lab.blind | lab.smart):
                try:
                    batch = helius.transactions(wallet, limit=100)
                except (RuntimeError, ValueError):
                    skips["provider_failure"] = skips.get("provider_failure", 0) + 1
                    continue
                timestamps = [x["timestamp"] for x in batch if isinstance(x.get("timestamp"), int)]
                if len(batch) == 100 and last_observed and timestamps and min(timestamps) >= last_observed:
                    skips["unverifiable_history_gap"] = skips.get("unverifiable_history_gap", 0) + 1
                    continue
                for tx in sorted(batch, key=lambda x: (x.get("timestamp") or 0, x.get("signature") or "")):
                    if tx.get("type") != "SWAP":
                        continue
                    t = parse_swap(tx, wallet=wallet, observed_at=now,
                                   historical_sol_usd=sol_price)
                    if t is None:
                        skips["unparsed_or_unsupported"] = skips.get("unparsed_or_unsupported", 0) + 1
                        continue
                    if t.key not in lab.seen:
                        new_mints.add(t.mint)
                        lab.ingest(t)
            polls += 1
            last_observed = now
            next_poll = now + args.poll_seconds
            # First indication is observed at receipt, never backdated.
            if new_mints:
                try:
                    quotes.update(market.tokens(new_mints, now=now))
                except (ValueError, RuntimeError):
                    skips["market_failure"] = skips.get("market_failure", 0) + 1
        # Refresh holdings every ten seconds for risk marks; poll/network lag
        # is included in real observed signal-to-fill time.
        due_mints = {t.mint for due, _, t, _ in lab.pending if due <= now}
        held_mints = ({h.mint for p in lab.portfolios.values() for h in p.holdings.values()}
                      if now % 10 == 0 else set())
        if due_mints or held_mints:
            try:
                quotes.update(market.tokens(due_mints | held_mints, now=now))
            except (RuntimeError, ValueError):
                skips["market_failure"] = skips.get("market_failure", 0) + 1
        lab.process(now, quotes)
        if last_observed and now % 15 == 0:
            write_json(path, snapshot(lab, quotes, now, polls, skips))
            write_json(Path(args.report), {**lab.report(quotes, now), "polls": polls, "skips": skips})
        time.sleep(1)
    now = int(time.time())
    write_json(path, snapshot(lab, quotes, now, polls, skips))
    write_json(Path(args.report), {**lab.report(quotes, now), "polls": polls, "skips": skips})
    print(f"Paper-only observation finished: {args.report}")


def cmd_report(args):
    doc = read_json(Path(args.state))
    lab = restore(doc)
    print(json.dumps({**lab.report(doc.get("quotes", {}), int(time.time())),
                      "polls": doc.get("polls", 0), "skips": doc.get("skips", {})},
                     indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description="YATL read-only Smart Money paper experiment")
    commands = parser.add_subparsers(dest="command", required=True)
    discover = commands.add_parser("discover", help="biased discovery candidates, NOT vetted wallets")
    discover.add_argument("--output", default="data/smart_money/candidates.json")
    discover.add_argument("--max-pools", type=int, default=5)
    discover.add_argument("--per-pool", type=int, default=30)
    screen_parser = commands.add_parser("screen", help="point-in-time history qualification")
    screen_parser.add_argument("--candidates", default="data/smart_money/candidates.json")
    screen_parser.add_argument("--output", default="data/smart_money/screened.json")
    screen_parser.add_argument("--max-wallets", type=int, default=30)
    screen_parser.add_argument("--max-pages", type=int, default=20)
    screen_parser.add_argument("--days", type=int, default=30)
    live = commands.add_parser("observe", help="live observed PAPER LEDGERS, never trading")
    live.add_argument("--screened", default="data/smart_money/screened.json")
    live.add_argument("--state", default="data/smart_money/state.json")
    live.add_argument("--report", default="data/smart_money/report.json")
    live.add_argument("--hours", type=int, default=24)
    live.add_argument("--poll-seconds", type=int, default=30)
    live.add_argument("--resume", action="store_true")
    report = commands.add_parser("report", help="print saved paper snapshot")
    report.add_argument("--state", default="data/smart_money/state.json")
    args = parser.parse_args(argv)
    if args.command == "discover":
        if not 1 <= args.max_pools <= 10 or not 1 <= args.per_pool <= 100:
            parser.error("discovery pool/page limit out of range")
        found = discover_candidates(Helius(os.getenv("HELIUS_API_KEY", "")), Market(),
                                    max_pools=args.max_pools, per_pool=args.per_pool)
        write_json(Path(args.output), found)
        print(json.dumps({"discovered_unverified": len(found), "output": args.output}))
    elif args.command == "screen":
        if not (1 <= args.max_wallets <= 100 and 1 <= args.max_pages <= 50
                and 30 <= args.days <= 90):
            parser.error("screen bounds exceeded")
        screen(args)
    elif args.command == "observe":
        if not (args.hours == 24 and 15 <= args.poll_seconds <= 600):
            parser.error("only fixed 24h experiment and >=15s polling allowed")
        observe(args)
    else:
        cmd_report(args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"SML stopped safely: {exc}", file=sys.stderr)
        sys.exit(2)
