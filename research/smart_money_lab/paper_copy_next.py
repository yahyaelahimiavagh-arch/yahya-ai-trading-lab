"""Forward PAPER COPY of six explicit Solana wallet candidates; NEVER submit orders.

A single $1000 hypothetical paper account follows observed, *new* leader swaps.
Fixed maximum $30 paper order; exits on first leader sell or modeled risk halt.
No hidden real-wallet keys, no sendTransaction, no swaps or broker connections.

This intentionally replaces the *experiment*, not the active V2 process.
Operator must stop V2 before beginning, preserving its audit files.
Helius shares the EXISTING persistent budget file; its 5000-call cap is never
reset. A no-network preflight is the default; start requires --start-paper.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sys
import time

from .engine import Holding, Portfolio, dec
from .providers import Helius, Market, classify_swap, valid_address

VERSION = "YATL_FORWARD_FIXED_NOTIONAL_PAPER_COPY_V1"
MAX_WALLETS = 6
MAX_CYCLES = 120
MAX_SIGNAL_AGE = 300


def _atomic(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",
                   encoding="utf-8")
    tmp.replace(path)


def _load_watchlist(path: Path):
    data=path.read_bytes()
    record=json.loads(data)
    if (record.get("schema")!="YATL_FORWARD_PAPER_COPY_WATCHLIST_V1"
            or record.get("allow_real_orders") is not False
            or not isinstance(record.get("wallets"),list)
            or len(record["wallets"])!=MAX_WALLETS):
        raise ValueError("expected six frozen paper-only candidates")
    wallets=[valid_address(x["wallet"]) for x in record["wallets"]]
    if len(set(wallets))!=MAX_WALLETS:
        raise ValueError("duplicate monitored wallets")
    return wallets,hashlib.sha256(data).hexdigest()


def _budget(path: Path) -> tuple[int,int]:
    if not path.is_absolute() or not path.is_file():
        raise ValueError("existing absolute V2 Helius budget file required; never reset")
    b=json.loads(path.read_text())
    used=b.get("calls")
    if type(used) is not int or not 0<=used<=5000:
        raise ValueError("invalid cumulative Helius budget count")
    return used,5000-used


def _old_observer_running() -> bool:
    """Best-effort Linux process check, not a substitute for operator shutdown."""
    proc=Path("/proc")
    if not proc.is_dir():
        return False
    for cmdline in proc.glob("[0-9]*/cmdline"):
        try:
            if int(cmdline.parent.name)==os.getpid():
                continue
            args=cmdline.read_bytes().replace(b"\x00",b" ").decode(
                "utf-8","ignore")
        except (PermissionError,FileNotFoundError,ProcessLookupError,ValueError):
            continue
        if ("research.smart_money_lab" in args and
                (" observe " in " "+args+" " or args.strip().endswith(" observe"))):
            return True
    return False


def _ensure_new_budget(polls: int,hours: int,wallet_count: int,remaining: int):
    if not (180<=polls<=600 and 1<=hours<=6 and wallet_count==MAX_WALLETS):
        raise ValueError("paper-pilot settings out of safe bounds")
    cycles=math.ceil(hours*3600/polls)
    expected=cycles*wallet_count
    # Retries on rate limit also consume reserved requests. We do not start
    # unless the old counter has headroom for a conservative 20% buffer.
    required=math.ceil(expected*1.2)+2*wallet_count
    if remaining<required:
        raise ValueError(
            f"insufficient EXISTING Helius budget: need {required}, "
            f"available {remaining}; do not reset or buy credits")
    return {"planned_cycles":cycles,"estimated_calls":expected,
            "minimum_remaining_calls":required,"remaining_before_start":remaining}


def _snapshot(account: Portfolio, *, started_at: int, finish_at: int,
              watchlist_sha: str, wallets: list[str], quotes: dict, seen: set[str],
              latest_poll: dict, last_seen_chain: dict, latest_source_sell: dict,
              skips: Counter, source_signals: int, cycles: int,
              status: str, halt_reason: str | None) -> dict:
    return {
        "kind":VERSION,"started_at":started_at,"finish_at":finish_at,
        "watchlist_sha256":watchlist_sha,"wallets":wallets,
        "state_status":status,"halt_reason":halt_reason,
        "cycles":cycles,"source_signals":source_signals,
        "seen":sorted(seen),"quotes":quotes,
        "latest_poll":latest_poll,"last_seen_chain":last_seen_chain,
        "latest_source_sell":latest_source_sell,"skips":dict(skips),
        "portfolio":{
            "cash":str(account.cash),"peak_equity":str(account.peak_equity),
            "halted":account.halted,"fills":account.fills,
            "rejected":account.rejected,
            "holdings":{k:{"wallet":v.wallet,"mint":v.mint,
                            "qty":str(v.qty),"cost":str(v.cost)}
                        for k,v in account.holdings.items()},
        },
    }


def _restore(state: dict, *, expected_hash: str, expected_wallets: list[str]):
    if (state.get("kind")!=VERSION or
            state.get("watchlist_sha256")!=expected_hash or
            state.get("wallets")!=expected_wallets):
        raise ValueError("refuse resume from different experiment or wallet selection")
    if state.get("state_status")=="completed":
        raise ValueError("paper experiment already completed")
    p=Portfolio("forward_copy",0)
    saved=state["portfolio"]
    p.cash=dec(saved["cash"])
    p.peak_equity=dec(saved["peak_equity"])
    p.halted=bool(saved["halted"])
    p.fills=saved["fills"]
    p.rejected=saved["rejected"]
    p.holdings={key:Holding(v["wallet"],v["mint"],dec(v["qty"]),dec(v["cost"]))
                for key,v in saved["holdings"].items()}
    return p


def _report(state: dict,now: int) -> dict:
    portfolio=_restore(state,expected_hash=state["watchlist_sha256"],
                       expected_wallets=state["wallets"]) if state["state_status"]!="completed" else None
    if portfolio is None:
        portfolio=Portfolio("forward_copy",0)
        saved=state["portfolio"]
        portfolio.cash=dec(saved["cash"])
        portfolio.peak_equity=dec(saved["peak_equity"])
        portfolio.halted=bool(saved["halted"])
        portfolio.fills=saved["fills"]
        portfolio.rejected=saved["rejected"]
        portfolio.holdings={k:Holding(v["wallet"],v["mint"],dec(v["qty"]),dec(v["cost"]))
                            for k,v in saved["holdings"].items()}
    data=portfolio.to_dict(state["quotes"],now)
    per_wallet=Counter()
    cashflow=Counter()
    previous_cash=dec("1000")
    for fill in portfolio.fills:
        wallet=fill.get("wallet")
        side=fill.get("side")
        next_cash=dec(fill["cash_after"])
        if wallet:
            per_wallet[wallet+"|"+side]+=1
            # Paper-only cashflow from actual modeled Portfolio cash changes.
            # Existing open position cost must be added back when deriving
            # realized contribution; its remaining value is still UNPRICED.
            cashflow[wallet]+=next_cash-previous_cash
        previous_cash=next_cash
    open_cost=Counter()
    for holding in portfolio.holdings.values():
        open_cost[holding.wallet]+=holding.cost
    attributed={}
    for wallet in state["wallets"]:
        pnl=cashflow[wallet]+open_cost[wallet]
        attributed[wallet]={
            "paper_buy_fills":per_wallet[wallet+"|BUY"],
            "paper_leader_sell_fills":per_wallet[wallet+"|SELL"],
            "paper_risk_exit_fills":per_wallet[wallet+"|RISK_EXIT"],
            "open_paper_position_cost_usd":str(open_cost[wallet]),
            "modeled_realized_pnl_usd":str(pnl),
            "caution":"Paper indicative fills only; not source wallet realized PnL",
        }
    return {
        "kind":"YATL_FORWARD_COPY_PAPER_REPORT",
        "note":"ONE portfolio; all orders are hypothetically modeled, NOT executable. These wallets are UNVETTED.",
        "started_at":state["started_at"],"as_of":now,
        "finish_at":state["finish_at"],"experiment_status":state["state_status"],
        "halt_reason":state["halt_reason"],
        "initial_usd":"1000","max_paper_entry_usd":"30",
        "watched_wallet_count":len(state["wallets"]),
        "source_signals":state["source_signals"],
        "cycles":state["cycles"],
        "last_polls_recent_count":sum(
            (type(t) is int and now-t<=600)
            for t in state["latest_poll"].values()),
        "paper_account":data,"paper_fills_by_wallet_side":dict(per_wallet),
        "per_wallet_modeled_realized_pnl":attributed,
        "skips":state["skips"],
        "equity_unknown":data["equity_usd"] is None,
        "realized_source_wallet_pnl":None,
        "execution_quote_verified":False,
        "helius_shared_budget_not_reset":True,
        "real_orders_submitted":0,
    }


def _quotes(market, mints, *, now, previous: dict):
    if not mints:
        return previous
    fetched=market.tokens(set(mints),now=now,fallback_limit=0)
    received=int(time.time())
    out=dict(previous)
    for mint,item in fetched.items():
        price=dec(item["price_usd"])
        liquidity=dec(item["liquidity_usd"])
        if price<=0 or liquidity<=0:
            continue
        out[mint]={"price_usd":str(price),"liquidity_usd":str(liquidity),
                   "ts":received}
    return out


def _parse_batch(raw, wallet, *, started_at: int, observed_at: int, sol_price):
    """Reject stale history, unknown trades, and source exits already in a batch."""
    swaps=[]
    skips=Counter()
    for tx in sorted(raw,key=lambda x:(x.get("timestamp") or 0,
                                       x.get("signature") or "")):
        stamp=tx.get("timestamp")
        if type(stamp) is not int or stamp<started_at:
            skips["historical_ignored"]+=1
            continue
        if stamp>observed_at or observed_at-stamp>MAX_SIGNAL_AGE:
            skips["late_signal"]+=1
            continue
        trade,why=classify_swap(tx,wallet=wallet,observed_at=observed_at,
                                historical_sol_usd=sol_price)
        if trade is None:
            skips["parse_"+why]+=1
            continue
        swaps.append(trade)
    sells={}
    for t in swaps:
        if t.side=="SELL":
            k=t.wallet+"|"+t.mint
            sells[k]=max(sells.get(k,0),t.chain_time)
    filtered=[]
    for t in swaps:
        k=t.wallet+"|"+t.mint
        if t.side=="BUY" and sells.get(k,0)>=t.chain_time:
            skips["leader_already_sold_before_observation"]+=1
            continue
        filtered.append(t)
    return filtered,skips,sells


def _apply_cycle(account, fresh_trades, quotes, *, now, seen, latest_source_sell, skips):
    """Paper fills only; no order interface is imported or exposed."""
    processed=0
    accepted=0
    for t in sorted(fresh_trades,key=lambda x:(x.chain_time,x.signature)):
        if t.key in seen:
            skips["duplicate_signal"]+=1
            continue
        seen.add(t.key)
        processed+=1
        k=t.wallet+"|"+t.mint
        if t.side=="BUY" and latest_source_sell.get(k,0)>=t.chain_time:
            skips["leader_position_already_closed"]+=1
            continue
        if t.side=="SELL":
            latest_source_sell[k]=max(latest_source_sell.get(k,0),t.chain_time)
        quote=quotes.get(t.mint)
        if quote is None:
            skips["missing_market_quote"]+=1
            continue
        if t.side=="BUY" and account.holdings:
            if account.equity(quotes,now) is None:
                # NEVER assume missing holdings have zero or stale value.
                account.halted=True
                skips["risk_locked_unpriced_holding"]+=1
                continue
        if now-t.chain_time>MAX_SIGNAL_AGE:
            skips["stale_before_paper_fill"]+=1
            continue
        if account.apply(t,price=dec(quote["price_usd"]),
                         liquidity_usd=dec(quote["liquidity_usd"]),
                         quote_ts=int(quote["ts"]),now=now):
            accepted+=1
    # Loss cap applies to PAPER only; marks are indicative not executable.
    if account.holdings and account.equity(quotes,now) is None:
        account.halted=True
        skips["risk_locked_unpriced_holding"]+=1
    else:
        account.mark(quotes,now)
    return processed,accepted


def start(args):
    wallets,sha=_load_watchlist(Path(args.watchlist))
    budget_path=Path(args.existing_budget_file).expanduser().resolve()
    used,left=_budget(budget_path)
    preflight=_ensure_new_budget(args.poll_seconds,args.hours,len(wallets),left)
    directory=Path(args.output_dir).expanduser().resolve()
    state_path=directory/"paper_copy_state.json"
    report_path=directory/"paper_copy_report.json"
    previous_observer_running=_old_observer_running()
    if previous_observer_running and args.start_paper:
        raise RuntimeError("V2 observer is still running. Stop and archive V2 BEFORE shared-budget paper-copy")
    if state_path.exists():
        if not args.resume:
            raise ValueError("existing paper-copy state found: use --resume or an empty output folder")
        state=json.loads(state_path.read_text(encoding="utf-8"))
        account=_restore(state,expected_hash=sha,expected_wallets=wallets)
        if state["finish_at"]<=int(time.time()):
            raise ValueError("original paper window finished; do not retroactively extend")
    else:
        if args.resume:
            raise ValueError("cannot resume nonexistent paper experiment")
        account=Portfolio("forward_copy",0)
        start_at=int(time.time())
        state=_snapshot(account,started_at=start_at,
                        finish_at=start_at+args.hours*3600,
                        watchlist_sha=sha,wallets=wallets,quotes={},seen=set(),
                        latest_poll={},last_seen_chain={},latest_source_sell={},
                        skips=Counter(),source_signals=0,cycles=0,
                        status="not_started",halt_reason=None)
    ready={
        "mode":"paper_only","wallets":len(wallets),
        "shared_budget_file":str(budget_path),
        "budget_calls_previously_used":used,
        "budget_calls_remaining":left,
        "preflight":preflight,
        "existing_state":state_path.exists(),
        "old_v2_observer_detected":previous_observer_running,
        "can_start_now":not previous_observer_running,
        "real_order_code_present":False,
        "output_dir":str(directory),
    }
    if not args.start_paper:
        print(json.dumps(ready,indent=2))
        return
    api=os.getenv("HELIUS_API_KEY","")
    if not api:
        raise ValueError("existing HELIUS_API_KEY must be loaded on VPS; NEVER print or paste it")
    os.environ["YATL_SML_HELIUS_BUDGET_FILE"]=str(budget_path)
    helius=Helius(api)
    market=Market()
    directory.mkdir(parents=True,exist_ok=True)
    seen=set(state["seen"])
    latest_poll=dict(state["latest_poll"])
    latest_chain=dict(state["last_seen_chain"])
    latest_sells=dict(state["latest_source_sell"])
    skips=Counter(state["skips"])
    source_signals=state["source_signals"]
    cycles=state["cycles"]
    quotes=dict(state["quotes"])
    shutdown=False

    def request_stop(*_):
        nonlocal shutdown
        shutdown=True

    signal.signal(signal.SIGTERM,request_stop)
    signal.signal(signal.SIGINT,request_stop)
    status="running"
    halt_reason=None
    print(json.dumps({
        "event":"paper_copy_started","paper_only":True,
        "candidate_wallets":len(wallets),"poll_seconds":args.poll_seconds,
        "duration_hours":args.hours,"old_shared_budget_remaining":left,
        "per_order_max_usd":"30","real_orders":0},sort_keys=True),flush=True)
    try:
        while int(time.time())<state["finish_at"] and not shutdown:
            start_mono=time.monotonic()
            fresh=[]
            sol_price=None
            sol_reference_attempted=False
            for wallet in wallets:
                try:
                    raw=helius.transactions(wallet,limit=100)
                except (RuntimeError,ValueError) as exc:
                    # Limit leakage: never print external URLs/keys or raw responses.
                    skips["helius_poll_error"]+=1
                    halt_reason="HELIUS_POLL_FAILURE_OR_BUDGET_GUARD"
                    status="halted_provider"
                    shutdown=True
                    break
                observed=int(time.time())
                times=[x.get("timestamp") for x in raw
                       if type(x.get("timestamp")) is int]
                if (len(raw)>=100 and times and
                    min(times)>=max(state["started_at"],latest_chain.get(wallet,0))):
                    skips["unverifiable_100_tx_history_gap"]+=1
                    halt_reason="UNVERIFIABLE_TRANSACTION_HISTORY_GAP"
                    status="halted_history_gap"
                    shutdown=True
                    break
                latest_poll[wallet]=observed
                latest_chain[wallet]=max(times,default=latest_chain.get(wallet,0))
                if not sol_reference_attempted:
                    sol_reference_attempted=True
                    try:
                        sol_price=market.sol_usd(now=observed)
                    except (RuntimeError,ValueError):
                        sol_price=None
                        skips["sol_price_unavailable"]+=1
                parsed,reason,sells=_parse_batch(
                    raw,wallet,started_at=state["started_at"],
                    observed_at=observed,sol_price=sol_price)
                fresh.extend(parsed)
                skips.update(reason)
                for k,value in sells.items():
                    latest_sells[k]=max(value,latest_sells.get(k,0))
            if shutdown:
                break
            now=int(time.time())
            mints={t.mint for t in fresh}
            mints.update(h.mint for h in account.holdings.values())
            try:
                quotes=_quotes(market,mints,now=now,previous=quotes)
            except (RuntimeError,ValueError):
                skips["market_quote_failure"]+=1
                # Unknown current prices block future purchases; existing
                # paper holdings may still be sold on a safely fresh quote.
                account.halted=True
                halt_reason="MARKET_QUOTES_UNAVAILABLE"
                status="halted_quote"
                shutdown=True
                break
            now=int(time.time())
            counts=_apply_cycle(account,fresh,quotes,now=now,seen=seen,
                                latest_source_sell=latest_sells,skips=skips)
            source_signals+=counts[0]
            cycles+=1
            state=_snapshot(account,started_at=state["started_at"],
                            finish_at=state["finish_at"],watchlist_sha=sha,
                            wallets=wallets,quotes=quotes,seen=seen,
                            latest_poll=latest_poll,last_seen_chain=latest_chain,
                            latest_source_sell=latest_sells,skips=skips,
                            source_signals=source_signals,cycles=cycles,
                            status="running",halt_reason=None)
            _atomic(state_path,state)
            _atomic(report_path,_report(state,now))
            equity=account.equity(quotes,now)
            print(json.dumps({
                "event":"paper_copy_cycle","cycle":cycles,
                "source_signals":source_signals,
                "paper_fills_total":len(account.fills),
                "paper_cash_usd":str(account.cash),
                "paper_equity_usd":str(equity) if equity is not None else None,
                "paper_open_positions":len(account.holdings),
                "entry_risk_halted":account.halted,
                "real_orders":0
            },sort_keys=True),flush=True)
            if account.halted:
                # Risk stop means stop opening new paper positions. Continue
                # to monitor SELL signals for remaining paper holdings.
                skips["paper_entry_risk_halt_active"]+=1
                if not account.holdings:
                    status="halted_risk"
                    halt_reason="PAPER_ACCOUNT_RISK_STOP"
                    break
            rest=args.poll_seconds-(time.monotonic()-start_mono)
            if rest>0 and not shutdown:
                # Signals terminate process safely while waiting.
                end_mono=time.monotonic()+rest
                while time.monotonic()<end_mono and not shutdown:
                    time.sleep(min(.5,end_mono-time.monotonic()))
    finally:
        if status=="running":
            status=("completed" if int(time.time())>=state["finish_at"] else
                    "interrupted")
        now=int(time.time())
        state=_snapshot(account,started_at=state["started_at"],
                        finish_at=state["finish_at"],watchlist_sha=sha,
                        wallets=wallets,quotes=quotes,seen=seen,
                        latest_poll=latest_poll,last_seen_chain=latest_chain,
                        latest_source_sell=latest_sells,skips=skips,
                        source_signals=source_signals,cycles=cycles,
                        status=status,halt_reason=halt_reason)
        _atomic(state_path,state)
        _atomic(report_path,_report(state,now))
        print(json.dumps({
            "status":status,"cycles":cycles,"source_signals":source_signals,
            "paper_fills":len(account.fills),"risk_halted":account.halted,
            "state":str(state_path),"report":str(report_path),
            "real_orders":0,"helius_budget_not_reset":True},indent=2))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--watchlist",required=True)
    p.add_argument("--existing-budget-file",required=True)
    p.add_argument("--output-dir",required=True)
    p.add_argument("--poll-seconds",type=int,default=300)
    p.add_argument("--hours",type=int,default=6)
    p.add_argument("--start-paper",action="store_true",
                   help="The ONLY mode that makes Helius requests; no real orders exist")
    p.add_argument("--resume",action="store_true")
    args=p.parse_args(argv)
    start(args)


if __name__=="__main__":
    try:
        main()
    except (ValueError,RuntimeError,FileNotFoundError,PermissionError) as exc:
        print("PAPER COPY STOPPED SAFELY: "+str(exc),file=sys.stderr)
        sys.exit(2)
