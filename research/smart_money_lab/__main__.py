"""Command line runner: discover -> screen -> 24h paper observe -> report.

No private key, sendTransaction, swap execution or broker integration exists.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import queue
import threading
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path
from decimal import Decimal
from collections import Counter

from .engine import PaperLab, Trade, Holding, dec, score_wallet, rank_wallets, DELAYS
from .pilot import exploratory_watchlist
from .dashboard import save_html
from .providers import Helius, Market, SOL, discover_candidates, get_json, parse_swap, classify_swap, valid_address


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
    reasons = Counter()
    for tx in raw:
        if tx.get("type") != "SWAP" or tx.get("feePayer") != wallet:
            continue
        swaps += 1
        chain_ts = tx.get("timestamp")
        hour = chain_ts // 3600 - 1 if isinstance(chain_ts, int) else -1
        t, reason = classify_swap(tx, wallet=wallet, observed_at=now,
                                  historical_sol_usd=prices.get(hour))
        if t is None:
            missed += 1
            reasons[reason] += 1
        else:
            trades.append(t)
    return trades, swaps, missed, dict(reasons)


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
    output_path = Path(args.output)
    previous = {}
    if getattr(args, "resume", False) and output_path.exists():
        rows = read_json(output_path)
        if not isinstance(rows, list):
            raise ValueError("existing screening output must be a JSON array")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("wallet"), str):
                raise ValueError("malformed previous screening row")
            if row["wallet"] in previous:
                raise ValueError("duplicate previous wallet rows")
            previous[row["wallet"]] = row
    scored = []
    for wallet in addresses:
        existing = previous.get(wallet)
        if existing is not None and not existing.get("error"):
            # Reuse the locally saved result; it is a research snapshot.
            # Wallet ranking remains fixed by the recorded cutoff.
            scored.append(existing)
            continue
        try:
            raw, complete = helius.history(
                wallet, earliest_ts=now - args.days * 86400, max_pages=args.max_pages)
            parsed, swaps, skipped, parse_reasons = parse_history(raw, wallet, now, prices)
            historical = [t for t in parsed if t.chain_time >= now - args.days * 86400]
            result = score_wallet(wallet, historical, cutoff=now, min_closed=50, min_days=15)
            result["history_complete"] = complete
            result["total_swaps_observed"] = swaps
            result["unparsed_swaps"] = skipped
            result["unparsed_swap_reasons"] = parse_reasons
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
                      "previous_rows_reused": sum(1 for r in scored if
                          previous.get(r.get("wallet")) is r),
                      "output": args.output}))


def trade_data(t: Trade) -> dict:
    return {**vars(t), "amount": str(t.amount), "usd_notional": str(t.usd_notional)}


def restore_trade(data: dict) -> Trade:
    return Trade(**{**data, "amount": dec(data["amount"]),
                    "usd_notional": dec(data["usd_notional"])})


def snapshot(lab: PaperLab, quotes: dict, now: int, polls: int, skips: dict, last_polls=None):
    return {
        "start_at": lab.start_at, "blind": sorted(lab.blind), "smart": sorted(lab.smart),
        "selection_mode": lab.selection_mode,
        "seen": sorted(lab.seen), "polls": polls, "skips": skips, "quotes": quotes,
        "last_polls": last_polls or {},
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
    lab = PaperLab(int(doc["start_at"]), list(doc["blind"]), list(doc["smart"]),
                   selection_mode=doc.get("selection_mode", "qualified"))
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



def observer_feed_health(*, wallets, last_polls: dict, started_at: int,
                         now: int, poll_seconds: int, collector_alive: bool) -> dict:
    """Read-only aggregate heartbeat. Never publish monitored wallet addresses.

    Fresh report files do not prove the collection thread is alive. All watched
    wallets must have a recent successful receipt to call the feed healthy.
    """
    if poll_seconds <= 0:
        raise ValueError("poll interval must be positive")
    expected = len(set(wallets))
    max_age = max(300, poll_seconds * 2 + 60)
    ages = []
    for wallet in set(wallets):
        timestamp = last_polls.get(wallet)
        if type(timestamp) is int and 0 < timestamp <= now:
            ages.append(now - timestamp)
    recent = sum(age <= max_age for age in ages)
    oldest_age = max(ages) if ages else None
    if not collector_alive:
        state = "collector_stopped"
    elif expected and recent == expected:
        state = "healthy"
    elif now - started_at <= max_age:
        state = "warming_up"
    else:
        state = "polls_stale"
    return {
        "state": state,
        "collector_alive": bool(collector_alive),
        "expected_wallets": expected,
        "recent_wallets": recent,
        "oldest_poll_age_seconds": oldest_age,
        "maximum_poll_age_seconds": max_age,
    }


def observe(args):
    """Concurrent READ acquisition; a single deterministic paper-account thread.

    Each batch records the time it finished downloading. The ledger scheduler
    keeps running while other wallet histories are still being fetched.
    """
    helius = Helius(os.getenv("HELIUS_API_KEY", ""))
    market = Market()
    path = Path(args.state)
    if path.exists():
        if not args.resume:
            raise ValueError("state already exists; use --resume or a new path")
        saved = read_json(path)
        lab = restore(saved)
        quotes = saved.get("quotes", {})
        polls, skips = saved.get("polls", 0), saved.get("skips", {})
        last_polls = saved.get("last_polls", {})
    else:
        screened = read_json(Path(args.screened))
        if not isinstance(screened, list):
            raise ValueError("screened must contain wallet records")
        strict_blind, strict_smart = rank_wallets(screened)
        if args.exploratory:
            # Always prefer strict selection; unvetted cohort is an explicit,
            # separate paper-only feed experiment when strict screening fails.
            if len(strict_smart) >= 2:
                raise ValueError("qualified wallets already available; omit --exploratory")
            blind, smart = exploratory_watchlist(screened)
            cohort = "exploratory_unvetted"
            print("WARNING: exploratory UNVETTED wallet sample. This is telemetry, "
                  "not a validated smart-money profitability experiment.", flush=True)
        else:
            if len(strict_smart) < 2:
                raise ValueError("need >=2 independently qualified wallets; "
                                 "only --exploratory can run an explicitly UNVETTED paper pilot")
            blind, smart = strict_blind, strict_smart
            cohort = "qualified"
        # Free-tier pilot: <=4 per strategy, up to 8 distinct monitored.
        # Extra 1/3/10-second delays are after observation, not end-to-end.
        lab = PaperLab(int(time.time()), blind[:4], smart[:4], selection_mode=cohort)
        quotes, polls, skips, last_polls = {}, 0, {}, {}
        write_json(path, snapshot(lab, quotes, lab.start_at, polls, skips, last_polls))
    finish = lab.start_at + args.hours * 3600
    if time.time() >= finish:
        raise ValueError("the original 24h window is already complete")

    results = queue.Queue(maxsize=200)
    stop = threading.Event()
    watched = sorted(lab.blind | lab.smart)

    def collector():
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as workers:
            while not stop.is_set():
                cycle_start = time.monotonic()
                tasks = {
                    workers.submit(helius.transactions, wallet, limit=100): wallet
                    for wallet in watched
                }
                for future in concurrent.futures.as_completed(tasks):
                    if stop.is_set():
                        break
                    wallet = tasks[future]
                    observed_at = int(time.time())
                    try:
                        batch = future.result()
                        record = ("batch", wallet, observed_at, batch)
                    except (RuntimeError, ValueError) as exc:
                        # Sanitized provider errors contain no URLs or API keys.
                        record = ("error", wallet, observed_at, str(exc)[:100])
                    except Exception:
                        # A previously unclassified network/library exception
                        # must not terminate this collector or leak secrets.
                        record = ("error", wallet, observed_at, "unexpected provider exception")
                    try:
                        results.put(record, timeout=1)
                    except queue.Full:
                        # A saturated pipeline cannot be treated as complete.
                        stop.set()
                        return
                elapsed = time.monotonic() - cycle_start
                stop.wait(max(0, args.poll_seconds - elapsed))

    worker = threading.Thread(target=collector, daemon=True, name="sml-read-only-poller")
    worker.start()
    next_save = time.monotonic() + 15
    next_mark = 0
    sol_price = None
    sol_price_time = 0
    interrupted = False

    def refresh(mints: set[str]):
        if not mints:
            return
        try:
            fetched = market.tokens(mints, now=int(time.time()), fallback_limit=3)
            receipt = int(time.time())
            for mint, q in fetched.items():
                quotes[mint] = {**q, "ts": receipt}
        except (ValueError, RuntimeError):
            skips["market_failure"] = skips.get("market_failure", 0) + 1

    try:
        while int(time.time()) < finish and not stop.is_set():
            # The observer's report writer can outlive a crashed collector.
            # Fail closed rather than continuing to advertise successful polling.
            if not worker.is_alive():
                skips["collector_stopped"] = skips.get("collector_stopped", 0) + 1
                stop.set()
                break
            new_mints = set()
            # Process ready wallet results without blocking on slower wallets.
            for _ in range(200):
                try:
                    kind, wallet, observed_at, batch = results.get_nowait()
                except queue.Empty:
                    break
                if kind == "error":
                    skips["provider_failure"] = skips.get("provider_failure", 0) + 1
                    if "safety cap reached" in batch:
                        skips["helius_budget_exhausted"] = skips.get("helius_budget_exhausted", 0) + 1
                        stop.set()
                    continue
                polls += 1
                raw_times = [x.get("timestamp") for x in batch
                             if isinstance(x.get("timestamp"), int)]
                prev = int(last_polls.get(wallet, 0))
                if (len(batch) == 100 and prev and raw_times
                        and min(raw_times) >= prev):
                    skips["unverifiable_history_gap"] = skips.get("unverifiable_history_gap", 0) + 1
                    last_polls[wallet] = observed_at
                    continue
                last_polls[wallet] = observed_at
                if observed_at - sol_price_time > 30:
                    try:
                        sol_price = market.sol_usd(now=observed_at)
                    except (RuntimeError, ValueError):
                        sol_price = None
                        skips["sol_quote_unavailable"] = skips.get("sol_quote_unavailable", 0) + 1
                    sol_price_time = int(time.time())
                for tx in sorted(batch, key=lambda x: (
                        x.get("timestamp") or 0, x.get("signature") or "")):
                    if tx.get("type") != "SWAP" or tx.get("feePayer") != wallet:
                        continue
                    chain_ts = tx.get("timestamp")
                    if not isinstance(chain_ts, int) or chain_ts < lab.start_at:
                        # Helius sends old history again in every poll. This is
                        # NOT a forward signal and must not create market API
                        # requests or inflate new-signal counts.
                        skips["historical_rows_ignored"] = skips.get("historical_rows_ignored", 0) + 1
                        continue
                    t, reason = classify_swap(tx, wallet=wallet,
                                              observed_at=observed_at,
                                              historical_sol_usd=sol_price)
                    if t is None:
                        key = "parse_" + reason
                        skips[key] = skips.get(key, 0) + 1
                        skips["unparsed_or_unsupported"] = skips.get("unparsed_or_unsupported", 0) + 1
                        continue
                    if t.key not in lab.seen:
                        # Do not request quotes for pre-start history or
                        # signals that are already too old to trade.
                        if observed_at - chain_ts <= 300:
                            new_mints.add(t.mint)
                        lab.ingest(t)
            refresh(new_mints)
            now = int(time.time())
            due_mints = {t.mint for due, _, t, _ in lab.pending if due <= now}
            if now >= next_mark:
                due_mints |= {h.mint for p in lab.portfolios.values() for h in p.holdings.values()}
                next_mark = now + 10
            refresh(due_mints)
            now = int(time.time())  # provider receipt latency counts toward fill
            lab.process(now, quotes)
            if time.monotonic() >= next_save:
                write_json(path, snapshot(lab, quotes, now, polls, skips, last_polls))
                health = observer_feed_health(
                    wallets=watched, last_polls=last_polls, started_at=lab.start_at,
                    now=now, poll_seconds=args.poll_seconds,
                    collector_alive=worker.is_alive())
                report_data = {**lab.report(quotes, now), "polls": polls, "skips": skips,
                               "feed_health": health,
                               "feed_complete": (
                                   health["state"] == "healthy" and not bool(
                                       skips.get("unverifiable_history_gap") or
                                       skips.get("provider_failure")))}
                write_json(Path(args.report), report_data)
                save_html(report_data, Path(args.html))
                next_save = time.monotonic() + 15
            time.sleep(0.25)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        stop.set()
        worker.join(timeout=15)
        now = int(time.time())
        # Final mark is never backdated and can remain unknown for illiquid mints.
        refresh({h.mint for p in lab.portfolios.values() for h in p.holdings.values()})
        lab.process(int(time.time()), quotes)
        now = int(time.time())
        write_json(path, snapshot(lab, quotes, now, polls, skips, last_polls))
        final_health = observer_feed_health(
            wallets=watched, last_polls=last_polls, started_at=lab.start_at,
            now=now, poll_seconds=args.poll_seconds,
            collector_alive=False)
        report_data = {**lab.report(quotes, now), "polls": polls,
                       "skips": skips, "interrupted": interrupted,
                       "feed_health": final_health,
                       "feed_complete": not bool(skips.get("unverifiable_history_gap") or
                                                 skips.get("provider_failure") or
                                                 skips.get("collector_stopped") or
                                                 (not interrupted and now < finish))}
        write_json(Path(args.report), report_data)
        save_html(report_data, Path(args.html))
    if interrupted:
        print(f"Paper observer stopped by operator; partial snapshot: {args.report}")
    elif now < finish:
        print(f"Paper observer halted on feed failure; partial snapshot: {args.report}")
    else:
        print(f"24h paper observer finished: {args.report}")

def cmd_report(args):
    doc = read_json(Path(args.state))
    lab = restore(doc)
    report_data = {**lab.report(doc.get("quotes", {}), int(time.time())),
                   "polls": doc.get("polls", 0), "skips": doc.get("skips", {})}
    if args.html:
        save_html(report_data, Path(args.html))
    print(json.dumps(report_data, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description="YATL read-only Smart Money paper experiment")
    commands = parser.add_subparsers(dest="command", required=True)
    discover = commands.add_parser("discover", help="biased discovery candidates, NOT vetted wallets")
    discover.add_argument("--output", default="data/smart_money/candidates.json")
    discover.add_argument("--max-pools", type=int, default=5)
    discover.add_argument("--per-pool", type=int, default=30)
    discover.add_argument("--source", choices=("boosts", "profiles"), default="boosts",
                          help="Profiles mode screens mature liquid pools but does NOT vet their traders")
    screen_parser = commands.add_parser("screen", help="point-in-time history qualification")
    screen_parser.add_argument("--candidates", default="data/smart_money/candidates.json")
    screen_parser.add_argument("--output", default="data/smart_money/screened.json")
    screen_parser.add_argument("--max-wallets", type=int, default=30)
    screen_parser.add_argument("--max-pages", type=int, default=20)
    screen_parser.add_argument("--days", type=int, default=30)
    screen_parser.add_argument("--resume", action="store_true",
                               help="retry previous error rows only; keep successful screening snapshots")
    live = commands.add_parser("observe", help="live observed PAPER LEDGERS, never trading")
    live.add_argument("--screened", default="data/smart_money/screened.json")
    live.add_argument("--state", default="data/smart_money/state.json")
    live.add_argument("--report", default="data/smart_money/report.json")
    live.add_argument("--html", default="data/smart_money/dashboard.html")
    live.add_argument("--hours", type=int, default=24)
    live.add_argument("--poll-seconds", type=int, default=180)
    live.add_argument("--resume", action="store_true")
    live.add_argument("--exploratory", action="store_true",
                      help="UNVETTED provisional wallet observation, paper only; no skill claim")
    report = commands.add_parser("report", help="print saved paper snapshot")
    report.add_argument("--state", default="data/smart_money/state.json")
    report.add_argument("--html", default=None)
    args = parser.parse_args(argv)
    if args.command == "discover":
        if not 1 <= args.max_pools <= 10 or not 1 <= args.per_pool <= 100:
            parser.error("discovery pool/page limit out of range")
        found = discover_candidates(Helius(os.getenv("HELIUS_API_KEY", "")), Market(),
                                    max_pools=args.max_pools, per_pool=args.per_pool,
                                    source=args.source)
        write_json(Path(args.output), found)
        print(json.dumps({"discovered_unverified": len(found), "output": args.output}))
    elif args.command == "screen":
        if not (1 <= args.max_wallets <= 100 and 1 <= args.max_pages <= 50
                and 30 <= args.days <= 90):
            parser.error("screen bounds exceeded")
        screen(args)
    elif args.command == "observe":
        if not (args.hours == 24 and 180 <= args.poll_seconds <= 600):
            parser.error("fixed 24h and >=180s polling required for free-tier pilot")
        observe(args)
    else:
        cmd_report(args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"SML stopped safely: {exc}", file=sys.stderr)
        sys.exit(2)
