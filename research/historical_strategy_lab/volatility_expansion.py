"""HSL-004B preregistered volatility-expansion technique candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Mapping, Sequence

from yatl.backtest import (
    BacktestClock, IntentAction, PaperFillEngine, PaperIntent,
    PortfolioLedger, apply_costs,
)
from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.strategy import FeatureError, LongSetup, StrategyAction, atr, rolling_high
from yatl.validation.paper_runner import RUNNER_QUANTITY
from yatl.validation.registration import CandidateFreeze

from research.crisis_lab import acquisition as acq
from research.crisis_lab import controls, replay
from . import walk_forward as hsl1

IMPLEMENTATION_ID = "HSL-004B-VOLATILITY-EXPANSION/0.1.0"
SCHEMA_VERSION = "0.1.0"
DEFAULT_PROTOCOL_PATH = Path(
    "docs/research/historical-strategy-lab/"
    "HSL-004B-VOLATILITY-EXPANSION-PROTOCOL-v0.1.0.json"
)
MAX_PROTOCOL_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 6 * 1024 * 1024
CANDIDATE_ID = "HSL004B-VOL-EXPANSION-1"
STRATEGY_ID = "VOLATILITY_EXPANSION_LONG"
STRATEGY_VERSION = "0.1.0"


class HSLVolatilityError(RuntimeError):
    pass


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _canonical_json(value):
    return (_json(value) + "\n").encode("utf-8")


def _sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def _plain(value):
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise HSLVolatilityError("HSL-004B arithmetic is not finite")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _number(value, label):
    try:
        result = Decimal(str(value))
    except Exception:
        raise HSLVolatilityError(f"{label} is not numeric") from None
    if not result.is_finite():
        raise HSLVolatilityError(f"{label} is not finite")
    return result


def load_protocol(path=DEFAULT_PROTOCOL_PATH):
    try:
        target = acq.assert_safe_runtime_path(path)
    except acq.AcquisitionError as exc:
        raise HSLVolatilityError(str(exc)) from None
    if target.is_symlink():
        raise HSLVolatilityError("symlink HSL-004B protocol is forbidden")
    try:
        payload = target.read_bytes()
    except OSError:
        raise HSLVolatilityError("cannot read HSL-004B protocol") from None
    if not payload or len(payload) > MAX_PROTOCOL_BYTES:
        raise HSLVolatilityError("HSL-004B protocol size is invalid")
    try:
        protocol = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HSLVolatilityError("HSL-004B protocol is invalid JSON") from None
    if not isinstance(protocol, dict):
        raise HSLVolatilityError("HSL-004B protocol must be an object")
    if (
        protocol.get("schema") != "YATL_HSL_TECHNIQUE_CANDIDATE_PROTOCOL"
        or protocol.get("version") != SCHEMA_VERSION
        or protocol.get("status") != "REGISTERED_BEFORE_HSL004B_OUTCOME_REPLAY"
        or protocol.get("checkpoint") != "HSL-004B"
        or protocol.get("technique_family") != "VOLATILITY_EXPANSION"
        or protocol.get("research_only") is not True
        or protocol.get("paper_only") is not True
        or protocol.get("p4_p10_untouched") is not True
        or protocol.get("p11_locked") is not True
        or protocol.get("live_master_lock") != "OFF"
        or protocol.get("trade_permission") is not False
        or protocol.get("order_endpoint") is not False
        or protocol.get("ai_direct_execution") is not False
        or protocol.get("source_corpus_id") != controls.CONTROL_CORPUS_ID
        or protocol.get("parent_walk_forward_protocol")
        != "HSL-001-WALK-FORWARD/0.1.0"
    ):
        raise HSLVolatilityError("HSL-004B protocol invariants are invalid")
    parent, _ = hsl1.load_protocol()
    candidate = protocol.get("candidate")
    methodology = protocol.get("methodology")
    gate = protocol.get("qualification_gate")
    expected = {
        "atr_period_hours": 14,
        "atr_baseline_period_hours": 48,
        "minimum_atr_expansion_ratio": "1.25",
        "breakout_lookback_hours": 20,
        "minimum_close_location": "0.75",
        "maximum_breakout_extension_atr": "1",
        "stop_atr_multiple": "1.25",
        "reward_risk": "2",
        "exit_atr_expansion_ratio": "1",
    }
    if (
        not isinstance(candidate, dict) or not isinstance(methodology, dict)
        or not isinstance(gate, dict)
        or candidate.get("candidate_id") != CANDIDATE_ID
        or candidate.get("strategy_id") != STRATEGY_ID
        or candidate.get("strategy_version") != STRATEGY_VERSION
        or candidate.get("role") != "TECHNIQUE_LIBRARY_CHALLENGER"
        or candidate.get("parameters") != expected
    ):
        raise HSLVolatilityError("HSL-004B candidate differs from preregistration")
    pm = parent["methodology"]
    if (
        methodology.get("folds") != "EXACT_HSL001_F001_TO_F005"
        or methodology.get("symbols") != list(acq.ALLOWED_SYMBOLS)
        or methodology.get("state_reset_at_each_evaluation_fold") is not True
        or methodology.get("market_history_available_point_in_time") is not True
        or methodology.get("p4_risk_veto_applied") is not False
        or methodology.get("fixed_quantity") != RUNNER_QUANTITY
        or methodology.get("fee_bps") != pm["fee_bps"]
        or methodology.get("slippage_bps") != pm["slippage_bps"]
        or methodology.get("execution") != pm["execution"]
        or methodology.get("terminal_open_position") != pm["terminal_open_position"]
        or methodology.get("parameter_search") is not False
        or methodology.get("outcome_driven_retuning") is not False
        or methodology.get("historical_outcomes_used_for_configuration_selection")
        is not False
    ):
        raise HSLVolatilityError("HSL-004B methodology differs from HSL-001")
    pg = parent["qualification_gate"]
    for key in (
        "minimum_completed_trades_total", "minimum_completed_trades_per_symbol",
        "require_positive_total_net_pnl", "require_positive_expectancy",
        "minimum_profit_factor", "minimum_positive_oos_cell_fraction",
        "maximum_single_trade_share_of_positive_pnl", "maximum_drawdown_fraction",
    ):
        if gate.get(key) != pg.get(key):
            raise HSLVolatilityError("HSL-004B gate differs from HSL-001")
    if (
        gate.get("use_for_hsl_research_only") is not True
        or gate.get("automatic_promotion_to_p10_p11_live") is not False
    ):
        raise HSLVolatilityError("HSL-004B gate authority is invalid")
    return protocol, _sha256(payload)


def _true_ranges(candles, decision_time_ms):
    visible = [c for c in candles if c.close_time_ms < decision_time_ms]
    if len(visible) < 2:
        return ()
    values = []
    for previous, current in zip(visible, visible[1:]):
        high, low, prev_close = (
            Decimal(current.high), Decimal(current.low), Decimal(previous.close)
        )
        values.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return tuple(values)


def _atr_baseline(candles, period, decision_time_ms):
    ranges = _true_ranges(candles, decision_time_ms)
    if len(ranges) < period:
        return None
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        return sum(ranges[-period:], Decimal(0)) / Decimal(period)


@dataclass(frozen=True, slots=True)
class VolatilityDecision:
    action: StrategyAction
    reason: str
    setup: LongSetup | None
    expansion_ratio: str | None

    def __post_init__(self):
        if (
            not isinstance(self.action, StrategyAction)
            or not isinstance(self.reason, str) or not self.reason
            or (self.action is StrategyAction.ENTER_LONG and not isinstance(self.setup, LongSetup))
            or (self.action is not StrategyAction.ENTER_LONG and self.setup is not None)
        ):
            raise HSLVolatilityError("HSL-004B decision is inconsistent")


def _evaluate(snapshot, decision_time_ms, *, in_position, protocol):
    p = protocol["candidate"]["parameters"]
    try:
        volatility = atr(snapshot.primary, int(p["atr_period_hours"]), decision_time_ms)
        boundary = rolling_high(
            snapshot.primary[:-1], int(p["breakout_lookback_hours"]), decision_time_ms
        )
    except FeatureError as exc:
        raise HSLVolatilityError("HSL-004B feature evaluation failed") from exc
    baseline = _atr_baseline(
        snapshot.primary, int(p["atr_baseline_period_hours"]), decision_time_ms
    )
    if not volatility.available or baseline is None or baseline <= 0:
        return VolatilityDecision(StrategyAction.NO_TRADE, "INSUFFICIENT_HISTORY", None, None)
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        ratio = volatility.value / baseline
    ratio_text = _plain(ratio)
    if in_position:
        if ratio <= Decimal(p["exit_atr_expansion_ratio"]):
            return VolatilityDecision(
                StrategyAction.EXIT_LONG, "VOLATILITY_NORMALIZED_EXIT", None, ratio_text
            )
        return VolatilityDecision(
            StrategyAction.NO_TRADE, "HOLD_VOLATILITY_POSITION", None, ratio_text
        )
    if not boundary.available:
        return VolatilityDecision(StrategyAction.NO_TRADE, "INSUFFICIENT_HISTORY", None, ratio_text)
    if ratio < Decimal(p["minimum_atr_expansion_ratio"]):
        return VolatilityDecision(
            StrategyAction.NO_TRADE, "ATR_EXPANSION_BELOW_THRESHOLD", None, ratio_text
        )
    latest = snapshot.latest_primary
    close, high, low = Decimal(latest.close), Decimal(latest.high), Decimal(latest.low)
    if close <= boundary.value:
        return VolatilityDecision(StrategyAction.NO_TRADE, "NO_BREAKOUT", None, ratio_text)
    candle_range = high - low
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        close_location = (close - low) / candle_range if candle_range > 0 else Decimal(0)
        extension = (
            (close - boundary.value) / volatility.value
            if volatility.value > 0 else Decimal("Infinity")
        )
    if (
        close_location < Decimal(p["minimum_close_location"])
        or extension > Decimal(p["maximum_breakout_extension_atr"])
    ):
        return VolatilityDecision(
            StrategyAction.NO_TRADE, "EXPANSION_QUALITY_FILTER", None, ratio_text
        )
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        invalidation = close - volatility.value * Decimal(p["stop_atr_multiple"])
        risk = close - invalidation
        target = close + risk * Decimal(p["reward_risk"])
    if invalidation <= 0 or risk <= 0:
        return VolatilityDecision(
            StrategyAction.NO_TRADE, "INVALID_PROTECTIVE_LEVELS", None, ratio_text
        )
    setup = LongSetup(_plain(close), _plain(invalidation), _plain(target))
    return VolatilityDecision(
        StrategyAction.ENTER_LONG, "VOLATILITY_EXPANSION_ENTRY", setup, ratio_text
    )


def _run_cell(*, corpus, fold, symbol, protocol):
    _, _, start, end = hsl1._fold_times(fold)
    try:
        dataset, dataset_sha = hsl1._dataset(
            corpus=corpus, symbol=symbol, evaluation_start_ms=start,
            evaluation_end_ms=end,
        )
    except hsl1.HSLImplementationError as exc:
        raise HSLVolatilityError(str(exc)) from None
    by_open = {x.open_time_ms: x for x in dataset.primary}
    if len(by_open) != len(dataset.primary):
        raise HSLVolatilityError("HSL-004B primary candles are duplicated")
    events = tuple(BacktestClock(dataset).events())
    analysis = tuple(x for x in dataset.primary if start <= x.open_time_ms < end)
    if not events or not analysis:
        raise HSLVolatilityError("HSL-004B fold is empty")

    engine = PaperFillEngine(symbol)
    ledger = PortfolioLedger(dataset.spec)
    open_cash = None
    pnls = []
    reasons = {}
    counts = dict(decision=0, missing_fill=0, stale_snapshot=0, entry_signal=0,
                  entry_gap_rejected=0, entry_fill=0, exit_fill=0)
    initial = Decimal(CandidateFreeze().initial_equity_quote)
    peak, max_dd = initial, Decimal(0)

    for event in events:
        counts["decision"] += 1
        fill_candle = by_open.get(event.eligible_fill_open_time_ms)
        if fill_candle is None:
            counts["missing_fill"] += 1
            continue
        if any(
            c.close_time_ms >= event.decision_time_ms
            for series in (event.snapshot.primary, event.snapshot.context, event.snapshot.regime)
            for c in series
        ):
            raise HSLVolatilityError("HSL-004B decision contains future data")
        decision = None
        if not replay._snapshot_is_fresh(event.snapshot):
            counts["stale_snapshot"] += 1
            intent = PaperIntent(IntentAction.HOLD, event.decision_time_ms)
        else:
            decision = _evaluate(
                event.snapshot, event.decision_time_ms,
                in_position=engine.has_position, protocol=protocol,
            )
            if decision.action is StrategyAction.ENTER_LONG:
                counts["entry_signal"] += 1
                opened = Decimal(fill_candle.open)
                stop, target = Decimal(decision.setup.invalidation_price), Decimal(decision.setup.target_price)
                if not stop < opened < target:
                    counts["entry_gap_rejected"] += 1
                    intent = PaperIntent(IntentAction.HOLD, event.decision_time_ms)
                else:
                    intent = PaperIntent(
                        IntentAction.ENTER_LONG, event.decision_time_ms, RUNNER_QUANTITY,
                        decision.setup.invalidation_price, decision.setup.target_price,
                    )
            elif decision.action is StrategyAction.EXIT_LONG:
                intent = PaperIntent(IntentAction.EXIT_LONG, event.decision_time_ms)
            else:
                intent = PaperIntent(IntentAction.HOLD, event.decision_time_ms)

        fills = tuple(apply_costs(x, dataset.spec) for x in engine.process(event, intent, fill_candle))
        if fills:
            ledger.apply_many(fills)
        for fill in fills:
            if fill.reference.action is IntentAction.ENTER_LONG:
                counts["entry_fill"] += 1
                if open_cash is not None:
                    raise HSLVolatilityError("HSL-004B overlapping trade accounting")
                open_cash = fill.cash_delta
            else:
                counts["exit_fill"] += 1
                if open_cash is None:
                    raise HSLVolatilityError("HSL-004B exit has no paired entry")
                with localcontext() as arithmetic:
                    arithmetic.prec = DECIMAL_PRECISION
                    pnls.append(open_cash + fill.cash_delta)
                open_cash = None
        snap = ledger.snapshot(fill_candle.open)
        peak, max_dd = hsl1._drawdown_update(snap.equity_quote, peak, max_dd)
        if decision is not None:
            reasons[decision.reason] = reasons.get(decision.reason, 0) + 1

    final = ledger.snapshot(analysis[-1].close)
    peak, max_dd = hsl1._drawdown_update(final.equity_quote, peak, max_dd)
    realized = sum(pnls, Decimal(0))
    if realized != final.realized_pnl_quote:
        raise HSLVolatilityError("HSL-004B accounting disagrees with ledger")
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    gp, gl, completed = sum(wins, Decimal(0)), -sum(losses, Decimal(0)), len(pnls)
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        net = final.equity_quote - initial
        net_return = net / initial
        expectancy = realized / completed if completed else None
        win_rate = Decimal(len(wins)) / completed if completed else None
        largest = max(wins) if wins else Decimal(0)
        largest_share = largest / gp if gp > 0 else None
    pf, pf_inf = hsl1._profit_factor(gp, gl)
    return {
        "fold_id": fold["fold_id"], "symbol": symbol, "candidate_id": CANDIDATE_ID,
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "role": "TECHNIQUE_LIBRARY_CHALLENGER", "input_dataset_sha256": dataset_sha,
        "training_outcomes_used_for_configuration": False,
        "evaluation_start_ms": start, "evaluation_end_exclusive_ms": end,
        "decision_count": counts["decision"], "missing_fill_decision_count": counts["missing_fill"],
        "stale_snapshot_decision_count": counts["stale_snapshot"],
        "entry_signal_count": counts["entry_signal"],
        "entry_gap_rejected_count": counts["entry_gap_rejected"],
        "entry_fill_count": counts["entry_fill"], "exit_fill_count": counts["exit_fill"],
        "completed_trades": completed, "wins": len(wins), "losses": len(losses),
        "breakeven_trades": completed - len(wins) - len(losses),
        "win_rate": _plain(win_rate), "expectancy_quote": _plain(expectancy),
        "gross_profit_quote": _plain(gp), "gross_loss_quote": _plain(gl),
        "profit_factor": pf, "profit_factor_infinite": pf_inf,
        "largest_positive_trade_quote": _plain(largest),
        "largest_trade_profit_share": _plain(largest_share),
        "initial_equity_quote": _plain(initial), "final_equity_quote": _plain(final.equity_quote),
        "net_pnl_after_costs_quote": _plain(net), "net_return_after_costs": _plain(net_return),
        "realized_closed_trade_pnl_quote": _plain(realized),
        "unrealized_liquidation_net_pnl_quote": _plain(final.unrealized_pnl_quote),
        "executed_fee_quote": _plain(final.total_fee_quote),
        "executed_slippage_quote": _plain(final.total_slippage_quote),
        "executed_total_cost_quote": _plain(final.total_fee_quote + final.total_slippage_quote),
        "maximum_drawdown_fraction": _plain(max_dd),
        "open_position_at_fold_end": engine.has_position,
        "terminal_position_forced_closed": False, "point_in_time_verified": True,
        "decision_reason_counts": dict(sorted(reasons.items())),
    }


def _aggregate(protocol, cells):
    c = protocol["candidate"]
    record = {"candidate_id": c["candidate_id"], "strategy_id": c["strategy_id"],
              "strategy_version": c["strategy_version"], "role": c["role"]}
    try:
        summary = hsl1._aggregate_candidate(
            candidate_record=record, cells=cells, gate=protocol["qualification_gate"]
        )
    except hsl1.HSLImplementationError as exc:
        raise HSLVolatilityError(str(exc)) from None
    summary["automatic_promotion"] = False
    summary["p10_evidence_effect"] = "NONE"
    summary["p11_locked"] = True
    summary["live_authorized"] = False
    return summary


def run_volatility_expansion(*, runtime_root, quality_manifest_relative_path,
                             quality_manifest_file_sha256,
                             protocol_path=DEFAULT_PROTOCOL_PATH):
    protocol, protocol_sha = load_protocol(protocol_path)
    parent, parent_sha = hsl1.load_protocol()
    try:
        corpus = controls._load_control_corpus(
            runtime_root=runtime_root,
            quality_manifest_relative_path=quality_manifest_relative_path,
            quality_manifest_file_sha256=quality_manifest_file_sha256,
        )
    except controls.ControlError as exc:
        raise HSLVolatilityError(str(exc)) from None
    cells = [
        _run_cell(corpus=corpus, fold=fold, symbol=symbol, protocol=protocol)
        for fold in parent["folds"] for symbol in acq.ALLOWED_SYMBOLS
    ]
    result = {
        "schema": "YATL_HSL_TECHNIQUE_CANDIDATE_RESULT",
        "schema_version": SCHEMA_VERSION, "implementation_id": IMPLEMENTATION_ID,
        "checkpoint": "HSL-004B", "technique_family": "VOLATILITY_EXPANSION",
        "protocol_relative_path": protocol_path.as_posix(), "protocol_sha256": protocol_sha,
        "parent_protocol_sha256": parent_sha, "source_corpus_id": corpus.event_id,
        "input_quality_manifest_relative_path": corpus.quality_manifest_relative_path,
        "input_quality_manifest_file_sha256": corpus.quality_manifest_file_sha256,
        "candidate": protocol["candidate"], "methodology": protocol["methodology"],
        "qualification_gate": protocol["qualification_gate"], "cells": cells,
        "candidate_summary": _aggregate(protocol, cells),
        "historical_outcomes_used_for_configuration_selection": False,
        "parameter_search_performed": False, "outcome_driven_retuning_performed": False,
        "research_only": True, "paper_only": True, "p4_policy_mutated": False,
        "p10_read": False, "p10_write_allowed": False, "p10_evidence_effect": "NONE",
        "p11_locked": True, "live_master_lock": "OFF", "trade_permission": False,
        "order_endpoint": False, "ai_direct_execution": False,
    }
    result["result_sha256"] = _sha256(_canonical_json(result))
    return result


def _relative_path(digest):
    return Path("historical-strategy-lab") / "technique-library" / "volatility-expansion-v0.1.0" / f"hsl-004b-{digest[:24]}.json"


def run_and_write_volatility_expansion(**kwargs):
    result = run_volatility_expansion(**kwargs)
    payload = _canonical_json(result)
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise HSLVolatilityError("HSL-004B artifact exceeds bounded size")
    digest = _sha256(payload)
    try:
        relative = acq._write_immutable(kwargs["runtime_root"], _relative_path(digest), payload)
    except acq.AcquisitionError as exc:
        raise HSLVolatilityError(str(exc)) from None
    return {
        "manifest_relative_path": relative, "manifest_file_sha256": digest,
        "result_sha256": result["result_sha256"],
        "candidate_summary": result["candidate_summary"], "research_only": True,
        "p10_write_allowed": False, "p11_locked": True,
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m research.historical_strategy_lab.volatility_expansion",
        description="YATL HSL-004B preregistered volatility-expansion technique",
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--quality-manifest", required=True)
    parser.add_argument("--quality-manifest-sha256", required=True)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)
    return parser


def main(argv: Sequence[str] | None = None):
    args = build_parser().parse_args(argv)
    try:
        result = run_and_write_volatility_expansion(
            runtime_root=args.runtime_root,
            quality_manifest_relative_path=args.quality_manifest,
            quality_manifest_file_sha256=args.quality_manifest_sha256,
            protocol_path=args.protocol,
        )
    except HSLVolatilityError as exc:
        print(_json({"code": "HSL004B_VOLATILITY_ERROR", "reason": str(exc),
                     "research_only": True, "p10_write_allowed": False, "p11_locked": True}))
        return 2
    print(_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
