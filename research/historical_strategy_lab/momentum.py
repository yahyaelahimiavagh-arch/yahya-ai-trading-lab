"""HSL-004A preregistered momentum technique candidate.

Research-only. Evaluates one fixed long-only Spot momentum hypothesis on the
exact HSL-001 walk-forward folds and admitted CRL Development corpus. It has no
network, credentials, account, order, AI execution, P4/P10 write or live
capability. Parameters are frozen by the HSL-004A protocol before outcome replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Mapping, Sequence

from yatl.backtest import (
    BacktestClock,
    IntentAction,
    PaperFillEngine,
    PaperIntent,
    PortfolioLedger,
    apply_costs,
)
from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.strategy import (
    FeatureError,
    LongSetup,
    StrategyAction,
    atr,
    ema,
    rsi,
    simple_return,
)
from yatl.validation.paper_runner import RUNNER_QUANTITY
from yatl.validation.registration import CandidateFreeze

from research.crisis_lab import acquisition as acq
from research.crisis_lab import controls, replay

from . import walk_forward as hsl1


IMPLEMENTATION_ID = "HSL-004A-MOMENTUM/0.1.0"
SCHEMA_VERSION = "0.1.0"
DEFAULT_PROTOCOL_PATH = Path(
    "docs/research/historical-strategy-lab/"
    "HSL-004A-MOMENTUM-PROTOCOL-v0.1.0.json"
)
MAX_PROTOCOL_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 6 * 1024 * 1024
CANDIDATE_ID = "HSL004A-MOMENTUM-24H-1"
STRATEGY_ID = "MOMENTUM_24H_LONG"
STRATEGY_VERSION = "0.1.0"


class HSLMomentumError(RuntimeError):
    """HSL-004A violated a preregistered research boundary."""


def _json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return (_json(value) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _plain(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise HSLMomentumError("HSL-004A arithmetic is not finite")
    if value == 0:
        return "0"
    if value.as_tuple().exponent < -40:
        value = value.quantize(
            Decimal("1e-40"),
            rounding=ROUND_HALF_EVEN,
        )
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _number(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception:
        raise HSLMomentumError(f"{label} is not numeric") from None
    if not result.is_finite():
        raise HSLMomentumError(f"{label} is not finite")
    return result


def load_protocol(
    path: Path = DEFAULT_PROTOCOL_PATH,
) -> tuple[dict[str, object], str]:
    try:
        target = acq.assert_safe_runtime_path(path)
    except acq.AcquisitionError as exc:
        raise HSLMomentumError(str(exc)) from None
    if target.is_symlink():
        raise HSLMomentumError("symlink HSL-004A protocol is forbidden")
    try:
        payload = target.read_bytes()
    except OSError:
        raise HSLMomentumError("cannot read HSL-004A protocol") from None
    if not payload or len(payload) > MAX_PROTOCOL_BYTES:
        raise HSLMomentumError("HSL-004A protocol size is invalid")
    try:
        protocol = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HSLMomentumError(
            "HSL-004A protocol is not canonical UTF-8 JSON"
        ) from None
    if not isinstance(protocol, dict):
        raise HSLMomentumError("HSL-004A protocol must be an object")

    if (
        protocol.get("schema") != "YATL_HSL_TECHNIQUE_CANDIDATE_PROTOCOL"
        or protocol.get("version") != SCHEMA_VERSION
        or protocol.get("status")
        != "REGISTERED_BEFORE_HSL004A_OUTCOME_REPLAY"
        or protocol.get("checkpoint") != "HSL-004A"
        or protocol.get("technique_family") != "MOMENTUM"
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
        raise HSLMomentumError("HSL-004A protocol invariants are invalid")

    parent, _ = hsl1.load_protocol()
    candidate = protocol.get("candidate")
    methodology = protocol.get("methodology")
    benchmarks = protocol.get("benchmarks")
    gate = protocol.get("qualification_gate")
    if (
        not isinstance(candidate, dict)
        or not isinstance(methodology, dict)
        or not isinstance(benchmarks, dict)
        or not isinstance(gate, dict)
    ):
        raise HSLMomentumError("HSL-004A protocol scope is incomplete")

    expected_parameters = {
        "entry_return_lookback_hours": 24,
        "minimum_entry_return_fraction": "0.03",
        "ema_period_hours": 24,
        "rsi_period_hours": 14,
        "minimum_rsi": "55",
        "maximum_rsi": "75",
        "atr_period_hours": 14,
        "stop_atr_multiple": "1.5",
        "reward_risk": "2",
        "exit_return_lookback_hours": 12,
        "exit_return_threshold_fraction": "0",
    }
    if (
        candidate.get("candidate_id") != CANDIDATE_ID
        or candidate.get("strategy_id") != STRATEGY_ID
        or candidate.get("strategy_version") != STRATEGY_VERSION
        or candidate.get("role") != "TECHNIQUE_LIBRARY_CHALLENGER"
        or candidate.get("parameters") != expected_parameters
    ):
        raise HSLMomentumError(
            "HSL-004A candidate differs from preregistration"
        )

    parent_methodology = parent["methodology"]
    if (
        methodology.get("folds") != "EXACT_HSL001_F001_TO_F005"
        or methodology.get("symbols") != list(acq.ALLOWED_SYMBOLS)
        or methodology.get("state_reset_at_each_evaluation_fold") is not True
        or methodology.get("market_history_available_point_in_time") is not True
        or methodology.get("p4_risk_veto_applied") is not False
        or methodology.get("fixed_quantity") != RUNNER_QUANTITY
        or methodology.get("fee_bps") != parent_methodology["fee_bps"]
        or methodology.get("slippage_bps") != parent_methodology["slippage_bps"]
        or methodology.get("execution") != parent_methodology["execution"]
        or methodology.get("terminal_open_position")
        != parent_methodology["terminal_open_position"]
        or methodology.get("parameter_search") is not False
        or methodology.get("outcome_driven_retuning") is not False
        or methodology.get(
            "historical_outcomes_used_for_configuration_selection"
        ) is not False
        or methodology.get("external_source_claim_used_as_proof") is not False
    ):
        raise HSLMomentumError(
            "HSL-004A methodology differs from preregistration"
        )

    if (
        benchmarks.get("cash_no_trade") is not True
        or benchmarks.get("buy_and_hold_reported") is not True
        or benchmarks.get("buy_and_hold_is_parameter_selector") is not False
        or benchmarks.get("prior_hsl_strategy_outcomes_are_parameter_selectors")
        is not False
    ):
        raise HSLMomentumError("HSL-004A benchmark rules are invalid")

    parent_gate = parent["qualification_gate"]
    for key in (
        "minimum_completed_trades_total",
        "minimum_completed_trades_per_symbol",
        "require_positive_total_net_pnl",
        "require_positive_expectancy",
        "minimum_profit_factor",
        "minimum_positive_oos_cell_fraction",
        "maximum_single_trade_share_of_positive_pnl",
        "maximum_drawdown_fraction",
    ):
        if gate.get(key) != parent_gate.get(key):
            raise HSLMomentumError(
                "HSL-004A gate differs from HSL-001 gate"
            )
    if (
        gate.get("use_for_hsl_research_only") is not True
        or gate.get("buy_and_hold_outperformance_required") is not False
        or gate.get("automatic_promotion_to_p10_p11_live") is not False
    ):
        raise HSLMomentumError("HSL-004A gate authority is invalid")

    return protocol, _sha256(payload)


@dataclass(frozen=True, slots=True)
class MomentumDecision:
    action: StrategyAction
    reason: str
    setup: LongSetup | None
    entry_return: str | None
    ema_value: str | None
    rsi_value: str | None
    atr_value: str | None
    exit_return: str | None

    def __post_init__(self):
        if (
            not isinstance(self.action, StrategyAction)
            or not isinstance(self.reason, str)
            or not self.reason
            or (
                self.action is StrategyAction.ENTER_LONG
                and not isinstance(self.setup, LongSetup)
            )
            or (
                self.action is not StrategyAction.ENTER_LONG
                and self.setup is not None
            )
        ):
            raise HSLMomentumError(
                "HSL-004A momentum decision is inconsistent"
            )

    def as_record(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "setup": (
                None
                if self.setup is None
                else {
                    "reference_price": self.setup.reference_price,
                    "invalidation_price": self.setup.invalidation_price,
                    "target_price": self.setup.target_price,
                }
            ),
            "entry_return": self.entry_return,
            "ema_value": self.ema_value,
            "rsi_value": self.rsi_value,
            "atr_value": self.atr_value,
            "exit_return": self.exit_return,
        }


def _evaluate(
    snapshot,
    decision_time_ms: int,
    *,
    in_position: bool,
    protocol: Mapping[str, object],
) -> MomentumDecision:
    params = protocol["candidate"]["parameters"]
    try:
        entry_return = simple_return(
            snapshot.primary,
            int(params["entry_return_lookback_hours"]),
            decision_time_ms,
        )
        average = ema(
            snapshot.primary,
            int(params["ema_period_hours"]),
            decision_time_ms,
        )
        strength = rsi(
            snapshot.primary,
            int(params["rsi_period_hours"]),
            decision_time_ms,
        )
        volatility = atr(
            snapshot.primary,
            int(params["atr_period_hours"]),
            decision_time_ms,
        )
        exit_return = simple_return(
            snapshot.primary,
            int(params["exit_return_lookback_hours"]),
            decision_time_ms,
        )
    except FeatureError as exc:
        raise HSLMomentumError(
            "HSL-004A feature evaluation failed"
        ) from exc

    values = {
        "entry_return": _plain(entry_return.value),
        "ema_value": _plain(average.value),
        "rsi_value": _plain(strength.value),
        "atr_value": _plain(volatility.value),
        "exit_return": _plain(exit_return.value),
    }

    if in_position:
        if not exit_return.available:
            return MomentumDecision(
                StrategyAction.NO_TRADE,
                "INSUFFICIENT_EXIT_HISTORY",
                None,
                **values,
            )
        if exit_return.value <= Decimal(
            params["exit_return_threshold_fraction"]
        ):
            return MomentumDecision(
                StrategyAction.EXIT_LONG,
                "MOMENTUM_REVERSAL_EXIT",
                None,
                **values,
            )
        return MomentumDecision(
            StrategyAction.NO_TRADE,
            "HOLD_MOMENTUM_POSITION",
            None,
            **values,
        )

    if not all(
        feature.available
        for feature in (entry_return, average, strength, volatility)
    ):
        return MomentumDecision(
            StrategyAction.NO_TRADE,
            "INSUFFICIENT_ENTRY_HISTORY",
            None,
            **values,
        )

    close = Decimal(snapshot.latest_primary.close)
    if entry_return.value < Decimal(
        params["minimum_entry_return_fraction"]
    ):
        return MomentumDecision(
            StrategyAction.NO_TRADE,
            "ENTRY_RETURN_BELOW_THRESHOLD",
            None,
            **values,
        )
    if close <= average.value:
        return MomentumDecision(
            StrategyAction.NO_TRADE,
            "PRICE_NOT_ABOVE_EMA",
            None,
            **values,
        )
    if not (
        Decimal(params["minimum_rsi"])
        <= strength.value
        <= Decimal(params["maximum_rsi"])
    ):
        return MomentumDecision(
            StrategyAction.NO_TRADE,
            "RSI_OUTSIDE_ENTRY_BAND",
            None,
            **values,
        )

    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        invalidation = (
            close
            - volatility.value
            * Decimal(params["stop_atr_multiple"])
        )
        risk = close - invalidation
        target = (
            close
            + risk * Decimal(params["reward_risk"])
        )
    if invalidation <= 0 or risk <= 0:
        return MomentumDecision(
            StrategyAction.NO_TRADE,
            "INVALID_PROTECTIVE_LEVELS",
            None,
            **values,
        )
    setup = LongSetup(
        _plain(close),
        _plain(invalidation),
        _plain(target),
    )
    return MomentumDecision(
        StrategyAction.ENTER_LONG,
        "MOMENTUM_ENTRY",
        setup,
        **values,
    )


def _buy_hold_return(analysis_primary) -> Decimal:
    if not analysis_primary:
        raise HSLMomentumError(
            "HSL-004A benchmark has no analysis candles"
        )
    start = Decimal(analysis_primary[0].open)
    end = Decimal(analysis_primary[-1].close)
    if start <= 0 or end <= 0:
        raise HSLMomentumError(
            "HSL-004A benchmark price is invalid"
        )
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        return end / start - Decimal(1)


def _run_cell(
    *,
    corpus: controls.AdmittedControlCorpus,
    fold: Mapping[str, object],
    symbol: str,
    protocol: Mapping[str, object],
) -> dict[str, object]:
    _, _, evaluation_start, evaluation_end = hsl1._fold_times(fold)
    try:
        dataset, dataset_sha = hsl1._dataset(
            corpus=corpus,
            symbol=symbol,
            evaluation_start_ms=evaluation_start,
            evaluation_end_ms=evaluation_end,
        )
    except hsl1.HSLImplementationError as exc:
        raise HSLMomentumError(str(exc)) from None

    by_open = {item.open_time_ms: item for item in dataset.primary}
    if len(by_open) != len(dataset.primary):
        raise HSLMomentumError(
            "HSL-004A primary candles are duplicated"
        )
    events = tuple(BacktestClock(dataset).events())
    if not events:
        raise HSLMomentumError(
            "HSL-004A fold has no decision events"
        )
    analysis_primary = tuple(
        item
        for item in dataset.primary
        if evaluation_start <= item.open_time_ms < evaluation_end
    )
    if not analysis_primary:
        raise HSLMomentumError(
            "HSL-004A fold has no analysis candles"
        )

    fill_engine = PaperFillEngine(symbol)
    ledger = PortfolioLedger(dataset.spec)
    open_trade_cash_delta: Decimal | None = None
    trade_pnls: list[Decimal] = []
    reason_counts: dict[str, int] = {}
    counts = {
        "decision": 0,
        "missing_fill": 0,
        "stale_snapshot": 0,
        "entry_signal": 0,
        "entry_gap_rejected": 0,
        "entry_fill": 0,
        "exit_fill": 0,
    }

    initial = Decimal(CandidateFreeze().initial_equity_quote)
    peak = initial
    maximum_drawdown_fraction = Decimal(0)

    for event in events:
        counts["decision"] += 1
        fill_candle = by_open.get(event.eligible_fill_open_time_ms)
        if fill_candle is None:
            counts["missing_fill"] += 1
            continue
        if not fill_candle.is_closed:
            raise HSLMomentumError(
                "HSL-004A fill candle is not closed"
            )
        if any(
            candle.close_time_ms >= event.decision_time_ms
            for series in (
                event.snapshot.primary,
                event.snapshot.context,
                event.snapshot.regime,
            )
            for candle in series
        ):
            raise HSLMomentumError(
                "HSL-004A decision contains future data"
            )

        decision = None
        if not replay._snapshot_is_fresh(event.snapshot):
            counts["stale_snapshot"] += 1
            intent = PaperIntent(
                IntentAction.HOLD,
                event.decision_time_ms,
            )
        else:
            decision = _evaluate(
                event.snapshot,
                event.decision_time_ms,
                in_position=fill_engine.has_position,
                protocol=protocol,
            )
            if decision.action is StrategyAction.ENTER_LONG:
                counts["entry_signal"] += 1
                opened = Decimal(fill_candle.open)
                stop = Decimal(
                    decision.setup.invalidation_price
                )
                target = Decimal(decision.setup.target_price)
                if not stop < opened < target:
                    counts["entry_gap_rejected"] += 1
                    intent = PaperIntent(
                        IntentAction.HOLD,
                        event.decision_time_ms,
                    )
                else:
                    intent = PaperIntent(
                        IntentAction.ENTER_LONG,
                        event.decision_time_ms,
                        RUNNER_QUANTITY,
                        decision.setup.invalidation_price,
                        decision.setup.target_price,
                    )
            elif decision.action is StrategyAction.EXIT_LONG:
                intent = PaperIntent(
                    IntentAction.EXIT_LONG,
                    event.decision_time_ms,
                )
            else:
                intent = PaperIntent(
                    IntentAction.HOLD,
                    event.decision_time_ms,
                )

        references = fill_engine.process(
            event,
            intent,
            fill_candle,
        )
        costed = tuple(
            apply_costs(item, dataset.spec)
            for item in references
        )
        if costed:
            ledger.apply_many(costed)

        for fill in costed:
            if fill.reference.action is IntentAction.ENTER_LONG:
                counts["entry_fill"] += 1
                if open_trade_cash_delta is not None:
                    raise HSLMomentumError(
                        "HSL-004A overlapping trade accounting"
                    )
                open_trade_cash_delta = fill.cash_delta
            else:
                counts["exit_fill"] += 1
                if open_trade_cash_delta is None:
                    raise HSLMomentumError(
                        "HSL-004A exit has no paired entry"
                    )
                with localcontext() as arithmetic:
                    arithmetic.prec = DECIMAL_PRECISION
                    trade_pnls.append(
                        open_trade_cash_delta + fill.cash_delta
                    )
                open_trade_cash_delta = None

        snapshot = ledger.snapshot(fill_candle.open)
        peak, maximum_drawdown_fraction = hsl1._drawdown_update(
            snapshot.equity_quote,
            peak,
            maximum_drawdown_fraction,
        )

        if decision is not None:
            reason_counts[decision.reason] = (
                reason_counts.get(decision.reason, 0) + 1
            )

    final_mark = analysis_primary[-1].close
    final_snapshot = ledger.snapshot(final_mark)
    peak, maximum_drawdown_fraction = hsl1._drawdown_update(
        final_snapshot.equity_quote,
        peak,
        maximum_drawdown_fraction,
    )

    realized = sum(trade_pnls, Decimal(0))
    if realized != final_snapshot.realized_pnl_quote:
        raise HSLMomentumError(
            "HSL-004A closed-trade accounting disagrees with ledger"
        )

    wins = [item for item in trade_pnls if item > 0]
    losses = [item for item in trade_pnls if item < 0]
    gross_profit = sum(wins, Decimal(0))
    gross_loss = -sum(losses, Decimal(0))
    completed = len(trade_pnls)
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        net = final_snapshot.equity_quote - initial
        net_return = net / initial
        expectancy = realized / completed if completed else None
        win_rate = Decimal(len(wins)) / completed if completed else None
        largest_positive = max(wins) if wins else Decimal(0)
        largest_share = (
            largest_positive / gross_profit
            if gross_profit > 0
            else None
        )
        buy_hold = _buy_hold_return(analysis_primary)
        excess = net_return - buy_hold

    profit_factor, profit_factor_infinite = hsl1._profit_factor(
        gross_profit, gross_loss
    )

    return {
        "fold_id": fold["fold_id"],
        "symbol": symbol,
        "candidate_id": CANDIDATE_ID,
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "role": "TECHNIQUE_LIBRARY_CHALLENGER",
        "input_dataset_sha256": dataset_sha,
        "training_outcomes_used_for_configuration": False,
        "evaluation_start_ms": evaluation_start,
        "evaluation_end_exclusive_ms": evaluation_end,
        "decision_count": counts["decision"],
        "missing_fill_decision_count": counts["missing_fill"],
        "stale_snapshot_decision_count": counts["stale_snapshot"],
        "entry_signal_count": counts["entry_signal"],
        "entry_gap_rejected_count": counts["entry_gap_rejected"],
        "entry_fill_count": counts["entry_fill"],
        "exit_fill_count": counts["exit_fill"],
        "completed_trades": completed,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven_trades": completed - len(wins) - len(losses),
        "win_rate": _plain(win_rate),
        "expectancy_quote": _plain(expectancy),
        "gross_profit_quote": _plain(gross_profit),
        "gross_loss_quote": _plain(gross_loss),
        "profit_factor": profit_factor,
        "profit_factor_infinite": profit_factor_infinite,
        "largest_positive_trade_quote": _plain(largest_positive),
        "largest_trade_profit_share": _plain(largest_share),
        "initial_equity_quote": _plain(initial),
        "final_equity_quote": _plain(final_snapshot.equity_quote),
        "net_pnl_after_costs_quote": _plain(net),
        "net_return_after_costs": _plain(net_return),
        "realized_closed_trade_pnl_quote": _plain(realized),
        "unrealized_liquidation_net_pnl_quote": _plain(
            final_snapshot.unrealized_pnl_quote
        ),
        "executed_fee_quote": _plain(final_snapshot.total_fee_quote),
        "executed_slippage_quote": _plain(
            final_snapshot.total_slippage_quote
        ),
        "executed_total_cost_quote": _plain(
            final_snapshot.total_fee_quote
            + final_snapshot.total_slippage_quote
        ),
        "maximum_drawdown_fraction": _plain(
            maximum_drawdown_fraction
        ),
        "buy_and_hold_return_fraction": _plain(buy_hold),
        "excess_return_vs_buy_and_hold_fraction": _plain(excess),
        "open_position_at_fold_end": fill_engine.has_position,
        "terminal_position_forced_closed": False,
        "point_in_time_verified": True,
        "decision_reason_counts": dict(sorted(reason_counts.items())),
    }


def _aggregate(
    *,
    protocol: Mapping[str, object],
    cells: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    candidate = protocol["candidate"]
    record = {
        "candidate_id": candidate["candidate_id"],
        "strategy_id": candidate["strategy_id"],
        "strategy_version": candidate["strategy_version"],
        "role": candidate["role"],
    }
    try:
        summary = hsl1._aggregate_candidate(
            candidate_record=record,
            cells=cells,
            gate=protocol["qualification_gate"],
        )
    except hsl1.HSLImplementationError as exc:
        raise HSLMomentumError(str(exc)) from None

    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        mean_buy_hold = (
            sum(
                (
                    _number(
                        item["buy_and_hold_return_fraction"],
                        "buy-and-hold return",
                    )
                    for item in cells
                ),
                Decimal(0),
            )
            / Decimal(len(cells))
        )
        mean_excess = (
            sum(
                (
                    _number(
                        item["excess_return_vs_buy_and_hold_fraction"],
                        "excess return",
                    )
                    for item in cells
                ),
                Decimal(0),
            )
            / Decimal(len(cells))
        )

    summary["mean_buy_and_hold_return_fraction"] = _plain(
        mean_buy_hold
    )
    summary["mean_excess_return_vs_buy_and_hold_fraction"] = _plain(
        mean_excess
    )
    summary["buy_and_hold_outperformance_required"] = False
    summary["automatic_promotion"] = False
    summary["p10_evidence_effect"] = "NONE"
    summary["p11_locked"] = True
    summary["live_authorized"] = False
    return summary


def run_momentum(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
    protocol_path: Path = DEFAULT_PROTOCOL_PATH,
) -> dict[str, object]:
    protocol, protocol_sha = load_protocol(protocol_path)
    parent, parent_sha = hsl1.load_protocol()
    try:
        corpus = controls._load_control_corpus(
            runtime_root=runtime_root,
            quality_manifest_relative_path=quality_manifest_relative_path,
            quality_manifest_file_sha256=quality_manifest_file_sha256,
        )
    except controls.ControlError as exc:
        raise HSLMomentumError(str(exc)) from None

    cells: list[dict[str, object]] = []
    for fold in parent["folds"]:
        for symbol in acq.ALLOWED_SYMBOLS:
            cells.append(
                _run_cell(
                    corpus=corpus,
                    fold=fold,
                    symbol=symbol,
                    protocol=protocol,
                )
            )

    summary = _aggregate(
        protocol=protocol,
        cells=cells,
    )
    result: dict[str, object] = {
        "schema": "YATL_HSL_TECHNIQUE_CANDIDATE_RESULT",
        "schema_version": SCHEMA_VERSION,
        "implementation_id": IMPLEMENTATION_ID,
        "checkpoint": "HSL-004A",
        "technique_family": "MOMENTUM",
        "protocol_relative_path": protocol_path.as_posix(),
        "protocol_sha256": protocol_sha,
        "parent_protocol_sha256": parent_sha,
        "source_corpus_id": corpus.event_id,
        "input_quality_manifest_relative_path": (
            corpus.quality_manifest_relative_path
        ),
        "input_quality_manifest_file_sha256": (
            corpus.quality_manifest_file_sha256
        ),
        "candidate": protocol["candidate"],
        "methodology": protocol["methodology"],
        "benchmarks": protocol["benchmarks"],
        "qualification_gate": protocol["qualification_gate"],
        "cells": cells,
        "candidate_summary": summary,
        "historical_outcomes_used_for_configuration_selection": False,
        "parameter_search_performed": False,
        "outcome_driven_retuning_performed": False,
        "research_only": True,
        "paper_only": True,
        "p4_policy_mutated": False,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "p11_locked": True,
        "live_master_lock": "OFF",
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
    }
    result["result_sha256"] = _sha256(_canonical_json(result))
    return result


def _relative_path(digest: str) -> Path:
    return (
        Path("historical-strategy-lab")
        / "technique-library"
        / "momentum-v0.1.0"
        / f"hsl-004a-{digest[:24]}.json"
    )


def run_and_write_momentum(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
    protocol_path: Path = DEFAULT_PROTOCOL_PATH,
) -> dict[str, object]:
    result = run_momentum(
        runtime_root=runtime_root,
        quality_manifest_relative_path=quality_manifest_relative_path,
        quality_manifest_file_sha256=quality_manifest_file_sha256,
        protocol_path=protocol_path,
    )
    payload = _canonical_json(result)
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise HSLMomentumError(
            "HSL-004A artifact exceeds bounded size"
        )
    digest = _sha256(payload)
    try:
        relative = acq._write_immutable(
            runtime_root,
            _relative_path(digest),
            payload,
        )
    except acq.AcquisitionError as exc:
        raise HSLMomentumError(str(exc)) from None
    return {
        "manifest_relative_path": relative,
        "manifest_file_sha256": digest,
        "result_sha256": result["result_sha256"],
        "candidate_summary": result["candidate_summary"],
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=(
            "python -m "
            "research.historical_strategy_lab.momentum"
        ),
        description=(
            "YATL HSL-004A preregistered momentum technique"
        ),
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--quality-manifest", required=True)
    parser.add_argument("--quality-manifest-sha256", required=True)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=DEFAULT_PROTOCOL_PATH,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_and_write_momentum(
            runtime_root=args.runtime_root,
            quality_manifest_relative_path=args.quality_manifest,
            quality_manifest_file_sha256=args.quality_manifest_sha256,
            protocol_path=args.protocol,
        )
    except HSLMomentumError as exc:
        print(
            json.dumps(
                {
                    "code": "HSL004A_MOMENTUM_ERROR",
                    "reason": str(exc),
                    "research_only": True,
                    "p10_write_allowed": False,
                    "p11_locked": True,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    print(
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
