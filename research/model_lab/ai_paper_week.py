"""Bounded ChatGPT shadow proposals and deterministic virtual accounting.

No exchange execution imports, credentials, provider API, or runtime integration.
An AI proposal has no quantity authority; this isolated simulator can veto it.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal, ROUND_DOWN, localcontext
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request


BASE_MAIN = "58b6c74a834d51f0d68e06fbe5f1885057e9df9a"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
PROFILES = {
    "conservative": {"risk": "0.0025", "exposure": "0.10"},
    "aggressive": {"risk": "0.01", "exposure": "0.25"},
}
SAFETY = {
    "paper_research_only": True, "live_master_lock": "OFF",
    "live": False, "order_endpoint": False, "ai_direct_execution": False,
    "futures": False, "leverage": False, "short": False,
    "withdrawal": False, "p10_read": False, "p10_write": False,
    "p11_locked": True, "fresh_oos_read": False, "recent_reserve_read": False,
    "selection_authorized": False, "benchmark_retry_authorized": False,
    "full_batch_authorized": False, "paid_api_authorized": False,
}
DAY = 86_400_000
MAX_BYTES = 128 * 1024
BUY_MULTIPLIER = Decimal("1.0005") * Decimal("1.001")
SELL_MULTIPLIER = Decimal("0.9995") * Decimal("0.999")
ROOT = Path(__file__).resolve().parents[1] / "experiments" / "ai_paper_week"
NUMBER = re.compile(r"-?(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,18})?\Z")


class PaperWeekError(ValueError):
    """Reject an unverifiable or unsafe shadow record."""


def canonical(record):
    return (json.dumps(record, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def digest(record):
    return hashlib.sha256(canonical(record)).hexdigest()


def source_digest():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def decimal(value, *, positive=False):
    if not isinstance(value, str) or not NUMBER.fullmatch(value):
        raise PaperWeekError("plain decimal string required")
    number = Decimal(value)
    if positive and number <= 0:
        raise PaperWeekError("positive number required")
    return number


def integer(value):
    if type(value) is not int or value < 0:
        raise PaperWeekError("nonnegative integer timestamp required")
    return value


def exact(record, keys):
    if not isinstance(record, dict) or set(record) != set(keys):
        raise PaperWeekError("unknown or missing fields")


def plain(number):
    return format(number, "f")


def make_protocol(start_ms):
    integer(start_ms)
    return {
        "schema": "YATL_AI_SHADOW_WEEK/1", "experiment_id": "AI-PAPER-WEEK-20261002",
        "base_main": BASE_MAIN, "source_sha256": source_digest(),
        "start_ms": start_ms, "end_ms": start_ms + 7 * DAY,
        "initial_equity_usdt": "10000", "profiles": deepcopy(PROFILES),
        "fee_bps_per_side": 10, "slippage_bps_per_side": 5,
        "decision_frequency": "DAILY", "fill_policy": "NEXT_OBSERVED_DAILY_QUOTE",
        "max_pending_age_ms": 36 * 3_600_000,
        "max_entry_price_change_fraction": "0.01",
        "max_open_positions_per_profile": 1,
        "max_observed_daily_loss_fraction": "0.02",
        "max_observed_drawdown_fraction": "0.10", "max_consecutive_losses": 3,
        "model_identity": "CHATGPT_RUNTIME_UNPINNED", "extra_api_budget_usd": "0",
        "safety": deepcopy(SAFETY),
    }


def validate_protocol(protocol):
    if not isinstance(protocol, dict) or "start_ms" not in protocol:
        raise PaperWeekError("missing protocol")
    if canonical(protocol) != canonical(make_protocol(protocol["start_ms"])):
        raise PaperWeekError("protocol/source/safety identity mismatch; STOP")


def ticker_url(symbol):
    if symbol not in SYMBOLS:
        raise PaperWeekError("symbol is outside the frozen Spot universe")
    return "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=" + symbol


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PaperWeekError("public quote redirect forbidden")


def fetch_snapshot():
    # Sole network capability: two fixed anonymous public-data GET requests.
    opener = urllib.request.build_opener(NoRedirect)
    tickers = {}
    for symbol in SYMBOLS:
        with opener.open(ticker_url(symbol), timeout=15) as response:
            payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise PaperWeekError("public quote response too large")
        tickers[symbol] = {"url": ticker_url(symbol), "raw": json.loads(payload)}
    snapshot = {"schema": "YATL_AI_PUBLIC_SNAPSHOT/1",
                "observed_at_ms": int(time.time() * 1000), "tickers": tickers}
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot):
    exact(snapshot, ("schema", "observed_at_ms", "tickers"))
    if snapshot["schema"] != "YATL_AI_PUBLIC_SNAPSHOT/1":
        raise PaperWeekError("snapshot schema mismatch")
    observed = integer(snapshot["observed_at_ms"])
    exact(snapshot["tickers"], SYMBOLS)
    source_times = []
    for symbol, evidence in snapshot["tickers"].items():
        exact(evidence, ("url", "raw"))
        raw = evidence["raw"]
        if evidence["url"] != ticker_url(symbol) or not isinstance(raw, dict):
            raise PaperWeekError("quote provenance mismatch")
        if raw.get("symbol") != symbol:
            raise PaperWeekError("quote symbol mismatch")
        closed = integer(raw.get("closeTime"))
        opened = integer(raw.get("openTime"))
        if not 23 * 3_600_000 <= closed - opened <= 25 * 3_600_000:
            raise PaperWeekError("ticker is not a rolling daily observation")
        if not 0 <= observed - closed <= 300_000:
            raise PaperWeekError("stale or future public quote; no paper fill")
        for key in ("lastPrice", "openPrice", "highPrice", "lowPrice"):
            decimal(raw.get(key), positive=True)
        if not decimal(raw["lowPrice"]) <= decimal(raw["lastPrice"]) <= decimal(raw["highPrice"]):
            raise PaperWeekError("quote is outside its observed range")
        source_times.append(closed)
    if max(source_times) - min(source_times) > 60_000:
        raise PaperWeekError("profile market observations are not synchronized")


def validate_decisions(decisions, snapshot, protocol):
    exact(decisions, ("schema", "snapshot_sha256", "created_at_ms", "model_identity", "profiles"))
    if (decisions["schema"] != "YATL_AI_SHADOW_PROPOSALS/1"
            or decisions["snapshot_sha256"] != digest(snapshot)
            or decisions["model_identity"] != protocol["model_identity"]):
        raise PaperWeekError("proposal identity mismatch")
    created = integer(decisions["created_at_ms"])
    if not 0 <= created - snapshot["observed_at_ms"] <= 900_000:
        raise PaperWeekError("proposal is backdated or stale")
    exact(decisions["profiles"], PROFILES)
    for proposal in decisions["profiles"].values():
        exact(proposal, ("action", "symbol", "stop_fraction", "rationale"))
        if proposal["action"] not in ("BUY", "SELL", "HOLD") or proposal["symbol"] not in SYMBOLS:
            raise PaperWeekError("unknown action or symbol")
        if proposal["action"] == "BUY":
            stop = decimal(proposal["stop_fraction"], positive=True)
            if not Decimal("0.02") <= stop <= Decimal("0.10"):
                raise PaperWeekError("stop distance outside preregistered range")
        elif proposal["stop_fraction"] is not None:
            raise PaperWeekError("stop only applies to entry proposals")
        if not isinstance(proposal["rationale"], str) or not 1 <= len(proposal["rationale"]) <= 2000:
            raise PaperWeekError("proposal rationale missing or too long")


def price(snapshot, symbol):
    return decimal(snapshot["tickers"][symbol]["raw"]["lastPrice"], positive=True)


def account():
    return {"cash": Decimal(10000), "position": None, "pending": None,
            "peak": Decimal(10000), "previous_equity": Decimal(10000),
            "max_drawdown": Decimal(0), "consecutive_losses": 0,
            "halted": False, "closed_trades": 0, "wins": 0,
            "fees": Decimal(0), "slippage": Decimal(0), "turnover": Decimal(0),
            "decisions": [], "fills": []}


def equity(state, snapshot):
    position = state["position"]
    return state["cash"] + (position["quantity"] * price(snapshot, position["symbol"])
                            if position else Decimal(0))


def close_position(state, snapshot, reason):
    position = state["position"]
    if not position:
        return
    mark = price(snapshot, position["symbol"])
    gross = position["quantity"] * mark
    proceeds = gross * SELL_MULTIPLIER
    pnl = proceeds - position["entry_cost"]
    state["cash"] += proceeds
    state["fees"] += gross * Decimal("0.9995") * Decimal("0.001")
    state["slippage"] += gross * Decimal("0.0005")
    state["turnover"] += gross * Decimal("0.9995")
    state["closed_trades"] += 1
    state["wins"] += int(pnl > 0)
    state["consecutive_losses"] = state["consecutive_losses"] + 1 if pnl < 0 else 0
    state["fills"].append({"side": "SELL", "symbol": position["symbol"],
                           "observed_at_ms": snapshot["observed_at_ms"],
                           "mark": plain(mark), "quantity": plain(position["quantity"]),
                           "net_realized_pnl_usdt": plain(pnl), "reason": reason})
    state["position"] = None


def circuit(state, snapshot):
    value = equity(state, snapshot)
    state["peak"] = max(state["peak"], value)
    drawdown = (state["peak"] - value) / state["peak"]
    state["max_drawdown"] = max(state["max_drawdown"], drawdown)
    daily_loss = (state["previous_equity"] - value) / state["previous_equity"]
    if daily_loss >= Decimal("0.02") or drawdown >= Decimal("0.10") or state["consecutive_losses"] >= 3:
        state["halted"] = True
        close_position(state, snapshot, "OBSERVED_RISK_CIRCUIT")


def fill_pending(state, snapshot, profile, protocol):
    pending = state["pending"]
    state["pending"] = None  # Proposals are consumed once, including rejected ones.
    if not pending:
        return
    proposal = pending["proposal"]
    observed = snapshot["observed_at_ms"]
    symbol = proposal["symbol"]
    if proposal["action"] == "HOLD":
        return
    if snapshot["tickers"][symbol]["raw"]["closeTime"] <= pending["created_at_ms"]:
        raise PaperWeekError("fill quote precedes the AI proposal")
    if observed - pending["created_at_ms"] > protocol["max_pending_age_ms"]:
        state["decisions"].append("STALE_PENDING_REJECTED")
        return
    if proposal["action"] == "SELL":
        if state["position"] and state["position"]["symbol"] == symbol:
            close_position(state, snapshot, "PRIOR_AI_EXIT_PROPOSAL")
        return
    if state["halted"] or state["position"]:
        state["decisions"].append("RISK_OR_EXISTING_POSITION_VETO")
        return
    mark = price(snapshot, symbol)
    reference = decimal(pending["reference_price"], positive=True)
    if abs(mark / reference - 1) > Decimal("0.01"):
        state["decisions"].append("ENTRY_PRICE_MOVED_OVER_1_PERCENT")
        return
    value = equity(state, snapshot)
    stop = mark * (1 - decimal(proposal["stop_fraction"]))
    unit_cost = mark * BUY_MULTIPLIER
    unit_risk = unit_cost - stop * SELL_MULTIPLIER
    # Risk includes estimated entry + stop-exit costs; size is never supplied by AI.
    risk_budget = value * Decimal(PROFILES[profile]["risk"])
    capital_budget = min(state["cash"], value * Decimal(PROFILES[profile]["exposure"]))
    quantity = min(risk_budget / unit_risk, capital_budget / unit_cost).quantize(
        Decimal("0.00000001"), rounding=ROUND_DOWN)
    if quantity <= 0:
        state["decisions"].append("ZERO_SIZE_VETO")
        return
    entry_cost = quantity * unit_cost
    target = (unit_cost + 2 * unit_risk) / SELL_MULTIPLIER
    state["cash"] -= entry_cost
    state["fees"] += quantity * mark * Decimal("1.0005") * Decimal("0.001")
    state["slippage"] += quantity * mark * Decimal("0.0005")
    state["turnover"] += quantity * mark * Decimal("1.0005")
    state["position"] = {"symbol": symbol, "quantity": quantity,
                         "entry_cost": entry_cost, "stop": stop, "target": target}
    state["fills"].append({"side": "BUY", "symbol": symbol,
                           "observed_at_ms": observed, "proposal_created_at_ms": pending["created_at_ms"],
                           "mark": plain(mark), "quantity": plain(quantity),
                           "planned_stop_loss_usdt": plain(quantity * unit_risk),
                           "reason": "PRIOR_AI_PROPOSAL_RISK_ALLOWED"})


def process(states, event, protocol, previous_time):
    exact(event, ("snapshot", "decisions", "previous_event_sha256"))
    snapshot, decisions = event["snapshot"], event["decisions"]
    validate_snapshot(snapshot)
    observed = snapshot["observed_at_ms"]
    if not protocol["start_ms"] <= observed <= protocol["end_ms"] + 2 * 3_600_000:
        raise PaperWeekError("observation outside the bounded experiment")
    if previous_time is not None and observed - previous_time < 20 * 3_600_000:
        raise PaperWeekError("duplicate or too-frequent daily observation")
    finished = observed >= protocol["end_ms"]
    if finished:
        if decisions is not None:
            raise PaperWeekError("new proposals forbidden at/after week end")
    else:
        validate_decisions(decisions, snapshot, protocol)
        if decisions["created_at_ms"] >= protocol["end_ms"]:
            raise PaperWeekError("new proposals must precede week end")
    for profile, state in states.items():
        position = state["position"]
        if position:
            mark = price(snapshot, position["symbol"])
            if mark <= position["stop"] or mark >= position["target"]:
                close_position(state, snapshot, "OBSERVED_STOP_OR_TARGET")
        circuit(state, snapshot)
        if finished:
            state["pending"] = None
            close_position(state, snapshot, "WEEK_END_VIRTUAL_LIQUIDATION")
        else:
            fill_pending(state, snapshot, profile, protocol)
        circuit(state, snapshot)
        if not finished:
            proposal = decisions["profiles"][profile]
            state["pending"] = {"proposal": proposal,
                                "created_at_ms": decisions["created_at_ms"],
                                "reference_price": plain(price(snapshot, proposal["symbol"]))}
        state["previous_equity"] = equity(state, snapshot)
    return finished


def replay(protocol, events):
    validate_protocol(protocol)
    states = {profile: account() for profile in PROFILES}
    previous_time, previous_hash, finished = None, None, False
    with localcontext() as context:
        context.prec = 40
        for event in events:
            if finished:
                raise PaperWeekError("experiment already closed")
            if event.get("previous_event_sha256") != previous_hash:
                raise PaperWeekError("event hash chain mismatch")
            finished = process(states, event, protocol, previous_time)
            previous_time = event["snapshot"]["observed_at_ms"]
            previous_hash = digest(event)
        accounts = {}
        for profile, state in states.items():
            snapshot = events[-1]["snapshot"] if events else None
            value = equity(state, snapshot) if snapshot else Decimal(10000)
            accounts[profile] = {
                "equity_usdt": plain(value), "cash_usdt": plain(state["cash"]),
                "net_pnl_usdt": plain(value - 10000),
                "observed_max_drawdown_fraction": plain(state["max_drawdown"]),
                "position": {k: plain(v) if isinstance(v, Decimal) else v
                             for k, v in state["position"].items()} if state["position"] else None,
                "pending_proposal": state["pending"], "risk_halted": state["halted"],
                "closed_trades": state["closed_trades"], "wins": state["wins"],
                "fees_usdt": plain(state["fees"]), "slippage_usdt": plain(state["slippage"]),
                "turnover_usdt": plain(state["turnover"]),
                "fills": state["fills"], "vetoes": state["decisions"],
            }
        benchmarks = {"cash_usdt": "10000", "profiles": {name: {} for name in PROFILES}}
        if len(events) >= 2:
            # Same delayed first-fill observation as an earliest AI entry, with both-side costs.
            first, last = events[1]["snapshot"], events[-1]["snapshot"]
            for name, limits in PROFILES.items():
                allocation = Decimal(10000) * Decimal(limits["exposure"])
                for symbol in SYMBOLS:
                    benchmarks["profiles"][name][symbol + "_passive_equity_usdt"] = plain(
                        Decimal(10000) - allocation + allocation / (price(first, symbol) * BUY_MULTIPLIER)
                        * price(last, symbol) * SELL_MULTIPLIER)
        return {"schema": "YATL_AI_SHADOW_WEEK_REPORT/1", "experiment_id": protocol["experiment_id"],
                "protocol_sha256": digest(protocol), "last_event_sha256": previous_hash,
                "status": "WEEK_CLOSED" if finished else "COLLECTING",
                "observation_count": len(events), "accounts": accounts, "benchmarks": benchmarks,
                "extra_api_cost_usd": "0", "safety": deepcopy(SAFETY),
                "limitations": ["Daily observations; intraday stops/gaps are not reconstructed.",
                                "Planned risk is not a guaranteed maximum loss.",
                                "Unrealized positions are marked; final positions include exit costs.",
                                "ChatGPT runtime model is not pinned; no paid provider is connected.",
                                "Passive comparisons match exposure caps, not stop risk or realized exposure.",
                                "Seven days cannot establish profitability or unlock any existing gate."]}


def safe_root(root):
    root = Path(root)
    if root.parent.resolve() != ROOT.resolve() or not re.fullmatch(r"[a-z0-9-]{3,80}", root.name):
        raise PaperWeekError("only the dedicated repository experiment directory is allowed")
    for path in (ROOT, root, root / "events", root / "protocol.json", root / "report.json"):
        if path.is_symlink():
            raise PaperWeekError("symlink experiment paths forbidden")
    return root


def safe_input_path(path):
    if path.parent.name != "inputs" or not re.fullmatch(r"[a-z0-9-]+\.json", path.name):
        raise PaperWeekError("quote/proposal files must be in dedicated experiment inputs")
    safe_root(path.parent.parent)
    if path.parent.is_symlink() or path.is_symlink():
        raise PaperWeekError("symlink input paths forbidden")
    return path


def load(path):
    if path.is_symlink():
        raise PaperWeekError("symlink input forbidden")
    # No input path may refer to a protected runtime or sealed research artifact.
    if any(part.lower() in {"p10", "p11", "fresh-oos", "fresh_oos", "recent-reserve", "recent_reserve"}
           for part in path.resolve().parts):
        raise PaperWeekError("protected input path forbidden")
    with path.open("rb") as handle:
        payload = handle.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise PaperWeekError("input too large")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PaperWeekError("duplicate JSON key")
            result[key] = value
        return result
    return json.loads(payload, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(PaperWeekError("nonfinite JSON")))


def history(root):
    event_dir = root / "events"
    if not event_dir.is_dir():
        raise PaperWeekError("missing event directory")
    paths = sorted(event_dir.iterdir())
    if len(paths) > 8 or [p.name for p in paths] != [f"{i:03d}.json" for i in range(len(paths))]:
        raise PaperWeekError("event sequence missing, duplicated or over budget")
    return [load(path) for path in paths]


def write_new(path, record):
    with path.open("xb") as handle:
        handle.write(canonical(record))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "quote", "step", "report"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "quote":
            if args.output:
                safe_input_path(args.output)
            snapshot = fetch_snapshot()
            if args.output:
                write_new(args.output, snapshot)
            print(canonical(snapshot).decode(), end="")
            return 0
        if not args.root:
            raise PaperWeekError("dedicated experiment root required")
        root = safe_root(args.root)
        if args.command == "init":
            protocol = make_protocol(int(time.time() * 1000))
            root.mkdir(parents=True, exist_ok=False)
            (root / "events").mkdir()
            (root / "inputs").mkdir()
            write_new(root / "protocol.json", protocol)
            report = replay(protocol, [])
        else:
            protocol, events = load(root / "protocol.json"), history(root)
            if args.command == "step":
                if not args.snapshot or len(events) >= 8:
                    raise PaperWeekError("snapshot required or observation budget exhausted")
                snapshot = load(safe_input_path(args.snapshot))
                now = int(time.time() * 1000)
                if not 0 <= now - snapshot["observed_at_ms"] <= 900_000:
                    raise PaperWeekError("step requires a current observation, not backfill")
                decisions = load(safe_input_path(args.decisions)) if args.decisions else None
                if decisions is not None and not 0 <= now - integer(decisions.get("created_at_ms")) <= 900_000:
                    raise PaperWeekError("step requires current, nonfuture AI proposal time")
                event = {"snapshot": snapshot, "decisions": decisions,
                         "previous_event_sha256": digest(events[-1]) if events else None}
                report = replay(protocol, events + [event])
                write_new(root / "events" / f"{len(events):03d}.json", event)
            else:
                report = replay(protocol, events)
        # Report is derived, never a source of quantity or accounting authority.
        (root / "report.json").write_bytes(canonical(report))
        print(canonical(report).decode(), end="")
        return 0
    except (PaperWeekError, OSError, ValueError, KeyError, TypeError) as exc:
        print(canonical({"status": "STOP", "reason": str(exc), "safety": SAFETY}).decode(), end="")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
