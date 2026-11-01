"""One Director-authorized June 2026 research replay; no provider AI or orders.

Reuses frozen P3 TREND_PULLBACK and accepted P2 next-open/protective fill model.
Only newly fetched public June candles are read. No sealed runtime is opened.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from decimal import Decimal, ROUND_DOWN, localcontext
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.request import build_opener

from yatl.backtest import DecisionEvent, IntentAction, PaperFillEngine, PaperIntent
from yatl.backtest.models import MarketSnapshot
from yatl.data import Candle, INTERVAL_MILLISECONDS, normalize_rest_kline
from yatl.data.rest import BinancePublicRestClient, NoPublicRedirects
from yatl.strategy import StrategyAction, StrategyContext
from yatl.strategy.trend import IDENTITY, PARAMETERS, evaluate_trend_pullback


BASE = "58b6c74a834d51f0d68e06fbe5f1885057e9df9a"
START, END = 1780272000000, 1782864000000
HOUR, DAY = 3_600_000, 86_400_000
SYMBOLS = ("BTCUSDT", "ETHUSDT")
PROFILES = {"conservative": {"risk": "0.0025", "exposure": "0.10"},
            "aggressive": {"risk": "0.01", "exposure": "0.25"}}
BUY = Decimal("1.0005") * Decimal("1.001")
SELL = Decimal("0.9995") * Decimal("0.999")
ROOT = Path(__file__).resolve().parents[1] / "experiments" / "june_2026_backtest"
SAFETY = {"paper_research_only": True, "live_master_lock": "OFF", "p11_locked": True,
          "live": False, "order_endpoint": False, "ai_direct_execution": False,
          "futures": False, "leverage": False, "short": False, "withdrawal": False,
          "p10_read": False, "p10_write": False, "recent_reserve_read": False,
          "fresh_oos_other_months_read": False, "june_2026_public_read_authorized": True,
          "selection_authorized": False, "benchmark_retry_authorized": False,
          "full_batch_authorized": False, "paid_api_authorized": False}


class JuneReplayError(ValueError):
    pass


def canonical(record):
    return (json.dumps(record, sort_keys=True, separators=(",", ":"),
                       allow_nan=False, ensure_ascii=False) + "\n").encode()


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def text(number):
    return format(number, "f")


def protocol():
    repo = Path(__file__).resolve().parents[2]
    dependency_hashes = {path.relative_to(repo).as_posix(): sha(path.read_bytes())
                         for path in sorted((repo / "yatl").rglob("*.py"))}
    return {"schema": "YATL_JUNE_PAPER_PROTOCOL/1", "experiment_id": "JUNE-2026-PAPER-001",
            "base_main": BASE, "module_sha256": sha(Path(__file__).read_bytes()),
            "dependency_source_sha256": sha(canonical(dependency_hashes)),
            "range_start_utc": "2026-06-01T00:00:00Z", "range_end_exclusive_utc": "2026-07-01T00:00:00Z",
            "start_ms": START, "end_ms": END, "symbols": list(SYMBOLS),
            "source": "https://data-api.binance.vision", "source_interval": "15m",
            "derived_intervals": ["1h", "4h"], "expected_source_rows_per_symbol": 2880,
            "strategy": {"id": IDENTITY.strategy_id, "version": IDENTITY.version,
                         "parameters": PARAMETERS}, "profiles": PROFILES, "initial_cash_usdt": "10000",
            "fee_bps_per_side": 10, "slippage_bps_per_side": 5,
            "warmup": "51 completed 4h bars, entirely within June; no earlier-month reads",
            "fill_policy": "NEXT_1H_OPEN; intrabar stop-first ambiguity; adverse opening gaps",
            "terminal_policy": "virtual liquidation at final June close with costs",
            "entry_priority": list(SYMBOLS), "max_open_positions_per_account": 1,
            "quantity_step": "0.000001", "lagged_hour_volume_participation_cap": "0.01",
            "daily_loss_latch_fraction": "0.02", "drawdown_latch_fraction": "0.10",
            "consecutive_loss_latch": 3, "circuit_execution": "next hour open; terminal close if at month end",
            "canonical_runs_max": 1, "parameter_search": False, "ai_decisions": False,
            "evidence_classification": "SEEN_RESEARCH_NOT_FRESH_OOS",
            "director_authorization": {"date_local": "2026-10-03", "timezone": "Europe/Istanbul",
                "confirmation": "باشه", "scope": "Only June 2026 BTC/ETH Spot paper backtest with two risk profiles",
                "consequence": "June 2026 has been exposed and cannot be independent Fresh OOS evidence"},
            "safety": SAFETY}


def validate_protocol(record):
    if canonical(record) != canonical(protocol()):
        raise JuneReplayError("protocol, source code, parameters or safety identity mismatch")


def aggregate(candles, interval):
    factor = INTERVAL_MILLISECONDS[interval] // INTERVAL_MILLISECONDS["15m"]
    output = []
    if len(candles) % factor:
        raise JuneReplayError("partial aggregate bar")
    with localcontext() as context:
        context.prec = 256
        for offset in range(0, len(candles), factor):
            group = candles[offset:offset + factor]
            output.append(replace(group[0], interval=interval, close_time_ms=group[-1].close_time_ms,
                high=text(max(Decimal(c.high) for c in group)), low=text(min(Decimal(c.low) for c in group)),
                close=group[-1].close, base_volume=text(sum((Decimal(c.base_volume) for c in group), Decimal(0))),
                quote_volume=text(sum((Decimal(c.quote_volume) for c in group), Decimal(0))),
                trade_count=sum(c.trade_count for c in group)))
    return tuple(output)


def admit(raw):
    if not isinstance(raw, dict) or set(raw) != set(SYMBOLS):
        raise JuneReplayError("frozen two-symbol dataset required")
    output = {}
    for symbol in SYMBOLS:
        rows = raw[symbol]
        if not isinstance(rows, list) or len(rows) != 2880:
            raise JuneReplayError("June must contain exactly 2880 contiguous 15m source rows")
        candles = tuple(normalize_rest_kline(symbol, "15m", row, END) for row in rows)
        expected = range(START, END, INTERVAL_MILLISECONDS["15m"])
        if [c.open_time_ms for c in candles] != list(expected):
            raise JuneReplayError("out-of-range, duplicate, unordered or missing June candle")
        output[symbol] = {"15m": candles, "1h": aggregate(candles, "1h"), "4h": aggregate(candles, "4h")}
    return output


def acquire():
    client = BinancePublicRestClient(base_url="https://data-api.binance.vision", max_attempts=1,
                                    opener=build_opener(NoPublicRedirects()))
    server = client.server_time()
    if server < END:
        raise JuneReplayError("month is not complete")
    raw, requests = {}, []
    for symbol in SYMBOLS:
        rows, cursor = [], START
        for _ in range(3):
            batch = client.klines(symbol, "15m", limit=1000, start_time=cursor, end_time=END - 1)
            if not batch:
                raise JuneReplayError("source returned an incomplete June page")
            requests.append({"symbol": symbol, "interval": "15m", "startTime": cursor,
                             "endTime": END - 1, "limit": 1000, "rows": len(batch),
                             "response_sha256": sha(canonical(batch))})
            rows.extend(batch)
            cursor = batch[-1][0] + INTERVAL_MILLISECONDS["15m"]
        raw[symbol] = rows
    admit(raw)
    return raw, {"schema": "YATL_JUNE_PUBLIC_DATA_MANIFEST/1", "host": "https://data-api.binance.vision",
                 "endpoint": "/api/v3/klines", "server_time_ms": server,
                 "retrieved_at_ms": int(time.time() * 1000), "requests": requests,
                 "datasets": {symbol: {"source_rows": 2880, "derived_1h_rows": 720,
                                        "derived_4h_rows": 180, "gaps": 0, "duplicates": 0,
                                        "raw_sha256": sha(canonical(raw[symbol]))} for symbol in SYMBOLS},
                 "classification": "SEEN_RESEARCH_NOT_FRESH_OOS", "safety": SAFETY}


def snapshot_at(data, symbol, at):
    series = data[symbol]
    return MarketSnapshot(symbol, at,
        tuple(c for c in series["1h"] if c.close_time_ms < at)[-64:],
        tuple(c for c in series["15m"] if c.close_time_ms < at)[-8:],
        tuple(c for c in series["4h"] if c.close_time_ms < at)[-51:])


def state():
    return {"cash": Decimal(10000), "position": None, "peak": Decimal(10000),
            "max_drawdown": Decimal(0), "max_exposure": Decimal(0), "day_start_equity": Decimal(10000),
            "loss_streak": 0, "halted": False, "halt_reason": None, "halt_time_ms": None,
            "fees": Decimal(0), "slippage": Decimal(0), "fills": [], "trades": [], "decisions": [],
            "counts": Counter(), "equity_curve": [], "turnover": Decimal(0)}


def equity(account, mark):
    position = account["position"]
    return account["cash"] + (position["quantity"] * mark if position else Decimal(0))


def observe(account, value, at):
    account["peak"] = max(account["peak"], value)
    dd = (account["peak"] - value) / account["peak"]
    account["max_drawdown"] = max(account["max_drawdown"], dd)
    loss = (account["day_start_equity"] - value) / account["day_start_equity"]
    if not account["halted"]:
        reason = ("DAILY_LOSS" if loss >= Decimal("0.02") else
                  "DRAWDOWN" if dd >= Decimal("0.10") else
                  "THREE_CONSECUTIVE_LOSSES" if account["loss_streak"] >= 3 else None)
        if reason:
            account["halted"], account["halt_reason"], account["halt_time_ms"] = True, reason, at


def record_fill(account, *, side, symbol, quantity, mark, at, reason, setup=None, planned_loss=None):
    gross = quantity * mark
    buying = side == "BUY"
    execution = mark * (Decimal("1.0005") if buying else Decimal("0.9995"))
    fee, slip = quantity * execution * Decimal("0.001"), gross * Decimal("0.0005")
    cash_delta = -quantity * execution - fee if buying else quantity * execution - fee
    account["cash"] += cash_delta
    account["fees"] += fee
    account["slippage"] += slip
    account["turnover"] += quantity * execution
    fill = {"side": side, "symbol": symbol, "at_ms": at, "quantity": text(quantity),
            "reference_price": text(mark), "execution_price": text(execution),
            "fee_usdt": text(fee), "slippage_usdt": text(slip), "reason": reason}
    if buying:
        if account["position"] or account["cash"] < 0:
            raise JuneReplayError("overlapping position or negative cash")
        account["position"] = {"symbol": symbol, "quantity": quantity,
            "entry_cost": -cash_delta, "entry_at_ms": at, "entry_price": mark, "setup": setup,
            "planned_loss": planned_loss}
        fill["planned_stop_loss_usdt"] = text(planned_loss)
    else:
        position = account["position"]
        if not position or position["symbol"] != symbol or position["quantity"] != quantity:
            raise JuneReplayError("exit position identity mismatch")
        pnl = position["entry_cost"] * -1 + cash_delta
        account["loss_streak"] = account["loss_streak"] + 1 if pnl < 0 else 0
        account["trades"].append({"symbol": symbol, "entry_at_ms": position["entry_at_ms"],
            "exit_at_ms": at, "net_pnl_usdt": text(pnl), "planned_stop_loss_usdt": text(position["planned_loss"]),
            "exit_reason": reason})
        account["position"] = None
    account["fills"].append(fill)


def entry_size(profile, cash, opened, stop, target, lagged_volume):
    if not stop < opened < target:
        return None, "NEXT_OPEN_OUTSIDE_BRACKET"
    loss_per_unit = opened * BUY - stop * SELL
    if target * SELL - opened * BUY <= 0:
        return None, "NONPOSITIVE_POST_COST_REWARD"
    limits = PROFILES[profile]
    quantity = min(cash * Decimal(limits["risk"]) / loss_per_unit,
                   cash * Decimal(limits["exposure"]) / (opened * BUY),
                   lagged_volume * Decimal("0.01")).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
    if quantity <= 0:
        return None, "ZERO_SIZE"
    if quantity * loss_per_unit > cash * Decimal(limits["risk"]) or quantity * opened * BUY > cash:
        raise JuneReplayError("sizing violates risk or cash budget")
    return (quantity, quantity * loss_per_unit), None


def run_profile(data, profile):
    account = state()
    engines = {symbol: PaperFillEngine(symbol) for symbol in SYMBOLS}
    by_time = {symbol: {c.open_time_ms: c for c in data[symbol]["1h"]} for symbol in SYMBOLS}
    for hour in range(4, 720):
        at = START + hour * HOUR
        position = account["position"]
        mark_open = Decimal(by_time[position["symbol"]][at].open) if position else Decimal(0)
        value_open = equity(account, mark_open)
        if hour == 4 or at % DAY == 0:
            account["day_start_equity"] = value_open
        observe(account, value_open, at)
        selected, setup, planned_loss = None, None, None
        decisions = []
        # All selections use the pre-bar state. A protective exit cannot permit re-entry in this hour.
        candidates = (position["symbol"],) if position else SYMBOLS
        for symbol in candidates:
            snap = snapshot_at(data, symbol, at)
            event = DecisionEvent(hour - 4, at, at, snap)
            decision = evaluate_trend_pullback(StrategyContext(IDENTITY, snap),
                in_position=bool(position), active_setup=position["setup"] if position else None)
            account["counts"][decision.reason.value] += 1
            decisions.append({"symbol": symbol, "action": decision.action.value,
                              "reason": decision.reason.value, "context_sha256": decision.context.context_sha256})
            bar = by_time[symbol][at]
            if position:
                action = IntentAction.EXIT_LONG if account["halted"] or decision.action is StrategyAction.EXIT_LONG else IntentAction.HOLD
                selected = (symbol, event, PaperIntent(action, at), bar)
            elif decision.action is StrategyAction.ENTER_LONG and selected is None:
                if account["halted"]:
                    account["counts"]["RISK_LATCH_VETO"] += 1
                    continue
                opened = Decimal(bar.open)
                size, veto = entry_size(profile, account["cash"], opened,
                    Decimal(decision.setup.invalidation_price), Decimal(decision.setup.target_price),
                    Decimal(snap.latest_primary.base_volume))
                if veto:
                    account["counts"][veto] += 1
                    continue
                quantity, planned_loss = size
                setup = decision.setup
                selected = (symbol, event, PaperIntent(IntentAction.ENTER_LONG, at, text(quantity),
                    setup.invalidation_price, setup.target_price), bar)
        account["decisions"].append({"at_ms": at, "observed": decisions,
                                     "selected_symbol": selected[0] if selected else None})
        if selected:
            symbol, event, intent, bar = selected
            for reference in engines[symbol].process(event, intent, bar):
                buying = reference.action is IntentAction.ENTER_LONG
                record_fill(account, side="BUY" if buying else "SELL", symbol=symbol,
                    quantity=Decimal(reference.quantity), mark=Decimal(reference.reference_price),
                    at=at, reason="RISK_CIRCUIT_EXIT" if account["halted"] else reference.reason.value,
                    setup=setup if buying else None, planned_loss=planned_loss if buying else None)
                if buying:
                    committed = account["position"]["entry_cost"] / value_open
                    account["max_exposure"] = max(account["max_exposure"], committed)
                observe(account, equity(account, Decimal(reference.reference_price)), at)
        position = account["position"]
        mark_close = Decimal(by_time[position["symbol"]][at].close) if position else Decimal(0)
        value = equity(account, mark_close)
        observe(account, value, at + HOUR - 1)
        account["equity_curve"].append({"at_ms": at + HOUR - 1, "equity_usdt": text(value)})
    position = account["position"]
    if position:
        record_fill(account, side="SELL", symbol=position["symbol"], quantity=position["quantity"],
                    mark=Decimal(data[position["symbol"]]["1h"][-1].close), at=END - 1,
                    reason="TERMINAL_VIRTUAL_LIQUIDATION")
        observe(account, account["cash"], END - 1)
        account["equity_curve"][-1]["equity_usdt"] = text(account["cash"])
    pnls = [Decimal(trade["net_pnl_usdt"]) for trade in account["trades"]]
    if sum(pnls, Decimal(0)) != account["cash"] - 10000:
        raise JuneReplayError("closed-trade PnL does not reconcile to terminal cash")
    gains, losses = sum((p for p in pnls if p > 0), Decimal(0)), -sum((p for p in pnls if p < 0), Decimal(0))
    return {"initial_equity_usdt": "10000", "final_equity_usdt": text(account["cash"]),
        "net_pnl_usdt": text(account["cash"] - 10000), "net_return_fraction": text((account["cash"] - 10000) / 10000),
        "max_observed_drawdown_fraction": text(account["max_drawdown"]),
        "max_committed_capital_fraction": text(account["max_exposure"]),
        "closed_trades": len(pnls), "wins": sum(p > 0 for p in pnls), "losses": sum(p < 0 for p in pnls),
        "win_rate": text(Decimal(sum(p > 0 for p in pnls)) / len(pnls)) if pnls else None,
        "profit_factor": text(gains / losses) if losses else None,
        "expectancy_usdt": text(sum(pnls, Decimal(0)) / len(pnls)) if pnls else None,
        "largest_loss_usdt": text(min((p for p in pnls if p < 0), default=Decimal(0))) if pnls else None,
        "fees_usdt": text(account["fees"]), "slippage_usdt": text(account["slippage"]),
        "turnover_usdt": text(account["turnover"]), "halted": account["halted"],
        "halt_reason": account["halt_reason"], "halt_time_ms": account["halt_time_ms"],
        "decision_counts": dict(account["counts"]), "open_positions_at_end": 0,
        "fills": account["fills"], "trades": account["trades"], "decisions": account["decisions"],
        "equity_curve": account["equity_curve"]}


def replay(raw, frozen_protocol):
    validate_protocol(frozen_protocol)
    data = admit(raw)
    with localcontext() as context:
        context.prec = 256
        accounts = {name: run_profile(data, name) for name in PROFILES}
        benchmarks = {}
        for name, limits in PROFILES.items():
            allocation = Decimal(10000) * Decimal(limits["exposure"])
            benchmarks[name] = {"cash_usdt": "10000"}
            for symbol in SYMBOLS:
                first = Decimal(data[symbol]["1h"][204].open)
                last = Decimal(data[symbol]["1h"][-1].close)
                quantity = (allocation / (first * BUY)).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
                benchmarks[name][symbol + "_passive_equity_usdt"] = text(Decimal(10000) - quantity * first * BUY + quantity * last * SELL)
    return {"schema": "YATL_JUNE_PAPER_RESULT/1", "status": "COMPLETED_SEEN_RESEARCH",
            "protocol_sha256": sha(canonical(frozen_protocol)), "base_main": BASE,
            "datasets_sha256": {s: sha(canonical(raw[s])) for s in SYMBOLS},
            "accounts": accounts, "benchmarks": benchmarks, "safety": SAFETY,
            "limitations": ["Rule-based frozen TREND_PULLBACK, not the ChatGPT forward experiment.",
                "June is now seen research; no independent OOS or promotion claim.",
                "No pre-June warmup; first 204 hours cannot satisfy 4h regime warmup.",
                "OHLC execution is hypothetical, protective ambiguity prioritizes stop; intrabar fill time unknown.",
                "Risk budgets do not guarantee maximum losses under gaps; circuits act next hour.",
                "Observed drawdown uses fills and hourly open/close marks, not the full tick path.",
                "Benchmark capital caps match; stop risk and realized exposure do not.",
                "One month cannot establish a stable profitable edge."]}


def safe_root(root):
    if root.resolve() != ROOT.resolve() or root.is_symlink():
        raise JuneReplayError("only the dedicated June experiment root is allowed")
    for name in ("protocol.json", "data", "results"):
        if (root / name).is_symlink():
            raise JuneReplayError("symlink experiment path forbidden")
    return root


def read(path, max_bytes=2_000_000):
    if path.is_symlink():
        raise JuneReplayError("symlink artifact forbidden")
    with path.open("rb") as handle:
        payload = handle.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise JuneReplayError("artifact too large")
    return json.loads(payload)


def write_new(path, record):
    with path.open("xb") as handle:
        handle.write(canonical(record))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "acquire", "run"))
    args = parser.parse_args(argv)
    root = safe_root(ROOT)
    if args.command == "freeze":
        root.mkdir(parents=True, exist_ok=False)
        write_new(root / "protocol.json", protocol())
        print("PROTOCOL_FROZEN=" + sha((root / "protocol.json").read_bytes()))
        return 0
    frozen = read(root / "protocol.json")
    validate_protocol(frozen)
    if args.command == "acquire":
        data_dir = root / "data"
        data_dir.mkdir(exist_ok=False)
        raw, manifest = acquire()
        for symbol in SYMBOLS:
            write_new(data_dir / (symbol + "-15m.json"), raw[symbol])
        write_new(data_dir / "manifest.json", manifest)
        print("JUNE_DATA_ADMITTED=" + sha(canonical(manifest)))
        return 0
    # Exclusive one-run reservation. Never delete/reuse after success or failure.
    run_dir = root / "results"
    run_dir.mkdir(exist_ok=False)
    write_new(run_dir / "reservation.json", {"protocol_sha256": sha(canonical(frozen)),
        "started_at_ms": int(time.time() * 1000), "runtime": sys.version, "canonical_run": 1})
    manifest = read(root / "data" / "manifest.json")
    raw = {symbol: read(root / "data" / (symbol + "-15m.json")) for symbol in SYMBOLS}
    for symbol in SYMBOLS:
        if manifest["datasets"][symbol]["raw_sha256"] != sha(canonical(raw[symbol])):
            raise JuneReplayError("admitted source dataset identity mismatch")
    result = replay(raw, frozen)
    summary = {**result, "accounts": {name: {k: v for k, v in account.items()
                if k not in ("fills", "trades", "decisions", "equity_curve")} for name, account in result["accounts"].items()}}
    for name, account in result["accounts"].items():
        write_new(run_dir / (name + "-ledger.json"), account)
    write_new(run_dir / "summary.json", summary)
    print(canonical(summary).decode(), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(canonical({"status": "STOP", "reason": str(error), "safety": SAFETY}).decode(), end="")
        raise SystemExit(2)
