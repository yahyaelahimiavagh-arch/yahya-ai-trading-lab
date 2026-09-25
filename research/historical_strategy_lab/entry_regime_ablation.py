"""HSL-003 deterministic single-filter entry/regime ablations.

Research-only. Reuses the exact HSL-001 folds, symbols, costs, fixed quantity
and point-in-time corpus. Each experiment removes at most one already-existing
entry filter. Exit logic and protective-level construction remain frozen.
No P4/P10 risk veto, production mutation, network, credentials or live authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, localcontext
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
    BREAKOUT_CONFIGURATION,
    BREAKOUT_IDENTITY,
    TREND_PULLBACK_CONFIGURATION,
    TREND_PULLBACK_IDENTITY,
    DecisionReason,
    FeatureError,
    LongSetup,
    MarketRegime,
    RegimeReason,
    StrategyAction,
    StrategyContext,
    StrategyDecision,
    atr,
    classify_regime,
    evaluate_breakout,
    evaluate_trend_pullback,
    rolling_high,
    rolling_low,
    sma,
)
from yatl.validation.paper_runner import RUNNER_QUANTITY
from yatl.validation.registration import CandidateFreeze

from research.crisis_lab import acquisition as acq
from research.crisis_lab import controls, replay

from . import walk_forward as hsl1


IMPLEMENTATION_ID = "HSL-003-ENTRY-REGIME-ABLATION/0.1.0"
SCHEMA_VERSION = "0.1.0"
DEFAULT_PROTOCOL_PATH = Path(
    "docs/research/historical-strategy-lab/"
    "HSL-003-ENTRY-REGIME-ABLATION-PROTOCOL-v0.1.0.json"
)
MAX_PROTOCOL_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 12 * 1024 * 1024

REMOVE_CONFIRMATION = "REMOVE_15M_BULLISH_CONFIRMATION"
REMOVE_REGIME = "REMOVE_TREND_UP_ENTRY_GATE_ONLY"
REMOVE_VOLATILITY_EXTENSION = "REMOVE_MAXIMUM_EXTENSION_ATR_ENTRY_GATE_ONLY"

_CONTROL_BY_STRATEGY = {
    "TREND_PULLBACK": "HSL003-TREND-CONTROL",
    "RANGE_BREAKOUT": "HSL003-BREAKOUT-CONTROL",
}


class HSLAblationError(RuntimeError):
    """HSL-003 violated a frozen research or safety boundary."""


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
    return hsl1._plain(value)


def _number(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception:
        raise HSLAblationError(f"{label} is not numeric") from None
    if not result.is_finite():
        raise HSLAblationError(f"{label} is not finite")
    return result


def load_protocol(
    path: Path = DEFAULT_PROTOCOL_PATH,
) -> tuple[dict[str, object], str]:
    try:
        target = acq.assert_safe_runtime_path(path)
    except acq.AcquisitionError as exc:
        raise HSLAblationError(str(exc)) from None
    if target.is_symlink():
        raise HSLAblationError("symlink HSL-003 protocol is forbidden")
    try:
        payload = target.read_bytes()
    except OSError:
        raise HSLAblationError("cannot read HSL-003 protocol") from None
    if not payload or len(payload) > MAX_PROTOCOL_BYTES:
        raise HSLAblationError("HSL-003 protocol size is invalid")
    try:
        protocol = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HSLAblationError(
            "HSL-003 protocol is not canonical UTF-8 JSON"
        ) from None
    if not isinstance(protocol, dict):
        raise HSLAblationError("HSL-003 protocol must be an object")
    if (
        protocol.get("schema") != "YATL_HSL_ENTRY_REGIME_ABLATION_PROTOCOL"
        or protocol.get("version") != SCHEMA_VERSION
        or protocol.get("status")
        != "REGISTERED_BEFORE_HSL003_OUTCOME_REPLAY"
        or protocol.get("research_only") is not True
        or protocol.get("paper_only") is not True
        or protocol.get("p4_p10_untouched") is not True
        or protocol.get("p11_locked") is not True
        or protocol.get("live_master_lock") != "OFF"
        or protocol.get("trade_permission") is not False
        or protocol.get("order_endpoint") is not False
        or protocol.get("ai_direct_execution") is not False
        or protocol.get("parent_protocol")
        != "HSL-001-WALK-FORWARD/0.1.0"
        or protocol.get("preceding_checkpoint")
        != "HSL-002-RISK-OVERLAY/0.1.0"
    ):
        raise HSLAblationError("HSL-003 protocol invariants are invalid")

    parent, _ = hsl1.load_protocol()
    methodology = protocol.get("methodology")
    experiments = protocol.get("experiments")
    non_experiments = protocol.get("non_experiments")
    gate = protocol.get("comparison_gate")
    if (
        not isinstance(methodology, dict)
        or not isinstance(experiments, list)
        or len(experiments) != 7
        or not isinstance(non_experiments, dict)
        or not isinstance(gate, dict)
    ):
        raise HSLAblationError("HSL-003 protocol scope is incomplete")

    if (
        methodology.get("folds") != "EXACT_HSL001_F001_TO_F005"
        or methodology.get("symbols") != list(acq.ALLOWED_SYMBOLS)
        or methodology.get("fixed_quantity") != RUNNER_QUANTITY
        or methodology.get("fee_bps")
        != parent["methodology"]["fee_bps"]
        or methodology.get("slippage_bps")
        != parent["methodology"]["slippage_bps"]
        or methodology.get("execution")
        != parent["methodology"]["execution"]
        or methodology.get("state_reset_at_each_evaluation_fold") is not True
        or methodology.get("market_history_available_point_in_time") is not True
        or methodology.get("p4_risk_veto_applied") is not False
        or methodology.get("parameter_search") is not False
        or methodology.get("post_hoc_combination") is not False
        or methodology.get("exit_logic_frozen") is not True
        or methodology.get("protective_level_logic_frozen") is not True
        or methodology.get("strategy_selection_from_prior_hsl_outcomes")
        is not False
    ):
        raise HSLAblationError(
            "HSL-003 methodology differs from HSL-001 boundaries"
        )

    expected = {
        "HSL003-TREND-CONTROL": ("TREND_PULLBACK", ()),
        "HSL003-TREND-NO-CONFIRMATION": (
            "TREND_PULLBACK", (REMOVE_CONFIRMATION,)
        ),
        "HSL003-TREND-NO-REGIME-ENTRY": (
            "TREND_PULLBACK", (REMOVE_REGIME,)
        ),
        "HSL003-BREAKOUT-CONTROL": ("RANGE_BREAKOUT", ()),
        "HSL003-BREAKOUT-NO-CONFIRMATION": (
            "RANGE_BREAKOUT", (REMOVE_CONFIRMATION,)
        ),
        "HSL003-BREAKOUT-NO-REGIME-ENTRY": (
            "RANGE_BREAKOUT", (REMOVE_REGIME,)
        ),
        "HSL003-BREAKOUT-NO-VOLATILITY-EXTENSION": (
            "RANGE_BREAKOUT", (REMOVE_VOLATILITY_EXTENSION,)
        ),
    }
    seen: set[str] = set()
    for item in experiments:
        if not isinstance(item, dict):
            raise HSLAblationError("HSL-003 experiment is invalid")
        experiment_id = item.get("experiment_id")
        strategy_id = item.get("strategy_id")
        changes = item.get("entry_changes")
        if (
            experiment_id not in expected
            or experiment_id in seen
            or not isinstance(changes, list)
            or len(changes) > 1
            or (strategy_id, tuple(changes)) != expected[experiment_id]
            or item.get("strategy_version") != "1.0.0"
        ):
            raise HSLAblationError(
                "HSL-003 experiment registration differs from frozen scope"
            )
        seen.add(str(experiment_id))
    if seen != set(expected):
        raise HSLAblationError("HSL-003 experiment set is incomplete")

    if (
        non_experiments.get("combined_filter_removal")
        != "FORBIDDEN_IN_HSL003"
        or non_experiments.get("parameter_retuning")
        != "FORBIDDEN_IN_HSL003"
        or not str(
            non_experiments.get("trend_volatility_filter_ablation", "")
        ).startswith("NOT_APPLICABLE")
    ):
        raise HSLAblationError("HSL-003 exclusions are not frozen")

    required_gate = {
        "minimum_completed_trades_total": 30,
        "minimum_completed_trades_per_symbol": 10,
        "require_positive_total_net_pnl": True,
        "require_positive_expectancy": True,
        "minimum_profit_factor": "1.05",
        "minimum_positive_oos_cell_fraction": "0.60",
        "maximum_single_trade_share_of_positive_pnl": "0.50",
        "maximum_drawdown_fraction": "0.10",
        "require_net_pnl_above_control": True,
        "require_expectancy_not_below_control": True,
        "automatic_strategy_mutation": False,
        "automatic_promotion_to_p10_p11_live": False,
    }
    if gate.get("research_only") is not True or any(
        gate.get(key) != value for key, value in required_gate.items()
    ):
        raise HSLAblationError("HSL-003 comparison gate is invalid")

    return protocol, _sha256(payload)


def _setup(
    reference: Decimal,
    invalidation: Decimal,
    reward_risk: Decimal,
) -> LongSetup | None:
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        risk = reference - invalidation
        target = reference + risk * reward_risk
    if invalidation <= 0 or risk <= 0:
        return None
    return LongSetup(
        _plain(reference),
        _plain(invalidation),
        _plain(target),
    )


def _target_record(
    *,
    change: str | None,
    passed: bool = False,
    blocked: bool = False,
) -> dict[str, object]:
    if passed and blocked:
        raise HSLAblationError("targeted filter cannot both pass and block")
    return {
        "target_filter": change,
        "target_filter_passed": passed,
        "target_filter_blocked": blocked,
    }


def _evaluate_trend(
    context: StrategyContext,
    *,
    in_position: bool,
    active_setup,
    change: str | None,
):
    if in_position or change is None:
        return (
            evaluate_trend_pullback(
                context,
                in_position=in_position,
                active_setup=active_setup,
            ),
            _target_record(change=change),
        )

    params = dict(TREND_PULLBACK_CONFIGURATION.values)
    try:
        regime = classify_regime(context)
        average = sma(
            context.snapshot.primary,
            params["primary_sma_period"],
            context.decision_time_ms,
        )
    except Exception as exc:
        raise HSLAblationError(
            "HSL-003 trend feature evaluation failed"
        ) from exc

    if regime.reason is RegimeReason.INSUFFICIENT_HISTORY or not average.available:
        return (
            StrategyDecision(
                context,
                StrategyAction.NO_TRADE,
                DecisionReason.INSUFFICIENT_HISTORY,
            ),
            _target_record(change=change),
        )

    target_passed = False
    target_blocked = False
    if change == REMOVE_REGIME:
        target_passed = regime.regime is MarketRegime.TREND_UP
        target_blocked = not target_passed
    else:
        if regime.regime is MarketRegime.UNKNOWN:
            return (
                StrategyDecision(
                    context,
                    StrategyAction.NO_TRADE,
                    DecisionReason.REGIME_UNKNOWN,
                ),
                _target_record(change=change),
            )
        if regime.regime is not MarketRegime.TREND_UP:
            return (
                StrategyDecision(
                    context,
                    StrategyAction.NO_TRADE,
                    DecisionReason.REGIME_BLOCKED,
                ),
                _target_record(change=change),
            )

    close = Decimal(context.snapshot.latest_primary.close)
    latest = context.snapshot.latest_primary
    if Decimal(latest.low) > average.value or close <= average.value:
        return (
            StrategyDecision(
                context,
                StrategyAction.NO_TRADE,
                DecisionReason.SETUP_ABSENT,
            ),
            _target_record(
                change=change,
                passed=target_passed,
                blocked=target_blocked,
            ),
        )

    confirmation = False
    if len(context.snapshot.context) >= 2:
        previous_15m, latest_15m = context.snapshot.context[-2:]
        confirmation = (
            Decimal(latest_15m.close) > Decimal(latest_15m.open)
            and Decimal(latest_15m.close)
            > Decimal(previous_15m.close)
        )
    if change == REMOVE_CONFIRMATION:
        target_passed = confirmation
        target_blocked = not confirmation
    elif not confirmation:
        return (
            StrategyDecision(
                context,
                StrategyAction.NO_TRADE,
                DecisionReason.CONFIRMATION_FAILED,
            ),
            _target_record(change=change),
        )

    try:
        volatility = atr(
            context.snapshot.primary,
            params["atr_period"],
            context.decision_time_ms,
        )
        recent_low = rolling_low(
            context.snapshot.primary,
            params["pullback_lookback"],
            context.decision_time_ms,
        )
    except FeatureError as exc:
        raise HSLAblationError(
            "HSL-003 trend level evaluation failed"
        ) from exc
    if not volatility.available or not recent_low.available:
        return (
            StrategyDecision(
                context,
                StrategyAction.NO_TRADE,
                DecisionReason.INSUFFICIENT_HISTORY,
            ),
            _target_record(
                change=change,
                passed=target_passed,
                blocked=target_blocked,
            ),
        )

    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        invalidation = Decimal(
            _plain(
                recent_low.value
                - volatility.value
                * Decimal(params["stop_atr_fraction"])
            )
        )
    setup = _setup(
        close,
        invalidation,
        Decimal(params["reward_risk"]),
    )
    if setup is None:
        return (
            StrategyDecision(
                context,
                StrategyAction.NO_TRADE,
                DecisionReason.SETUP_ABSENT,
            ),
            _target_record(
                change=change,
                passed=target_passed,
                blocked=target_blocked,
            ),
        )
    return (
        StrategyDecision(
            context,
            StrategyAction.ENTER_LONG,
            DecisionReason.TREND_PULLBACK_ENTRY,
            setup,
        ),
        _target_record(
            change=change,
            passed=target_passed,
            blocked=target_blocked,
        ),
    )


def _evaluate_breakout(
    context: StrategyContext,
    *,
    in_position: bool,
    active_setup,
    change: str | None,
):
    if in_position or change is None:
        return (
            evaluate_breakout(
                context,
                in_position=in_position,
                active_setup=active_setup,
            ),
            _target_record(change=change),
        )

    params = dict(BREAKOUT_CONFIGURATION.values)
    primary = context.snapshot.primary
    try:
        regime = classify_regime(context)
        boundary = rolling_high(
            primary[:-1],
            params["breakout_lookback"],
            context.decision_time_ms,
        )
        volatility = atr(
            primary[:-1],
            params["atr_period"],
            context.decision_time_ms,
        )
    except Exception as exc:
        raise HSLAblationError(
            "HSL-003 breakout feature evaluation failed"
        ) from exc

    if (
        regime.reason is RegimeReason.INSUFFICIENT_HISTORY
        or not boundary.available
        or not volatility.available
    ):
        return (
            StrategyDecision(
                context,
                StrategyAction.NO_TRADE,
                DecisionReason.INSUFFICIENT_HISTORY,
            ),
            _target_record(change=change),
        )

    target_passed = False
    target_blocked = False
    if change == REMOVE_REGIME:
        target_passed = regime.regime is MarketRegime.TREND_UP
        target_blocked = not target_passed
    else:
        if regime.regime is MarketRegime.UNKNOWN:
            return (
                StrategyDecision(
                    context,
                    StrategyAction.NO_TRADE,
                    DecisionReason.REGIME_UNKNOWN,
                ),
                _target_record(change=change),
            )
        if regime.regime is not MarketRegime.TREND_UP:
            return (
                StrategyDecision(
                    context,
                    StrategyAction.NO_TRADE,
                    DecisionReason.REGIME_BLOCKED,
                ),
                _target_record(change=change),
            )

    latest = context.snapshot.latest_primary
    close = Decimal(latest.close)
    if close <= boundary.value:
        return (
            StrategyDecision(
                context,
                StrategyAction.NO_TRADE,
                DecisionReason.SETUP_ABSENT,
            ),
            _target_record(
                change=change,
                passed=target_passed,
                blocked=target_blocked,
            ),
        )

    high = Decimal(latest.high)
    low = Decimal(latest.low)
    candle_range = high - low
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        close_location = (
            (close - low) / candle_range
            if candle_range > 0
            else Decimal(0)
        )
        extension_atr = (
            (close - boundary.value) / volatility.value
            if volatility.value > 0
            else Decimal("Infinity")
        )

    if close_location < Decimal(params["minimum_close_location"]):
        return (
            StrategyDecision(
                context,
                StrategyAction.NO_TRADE,
                DecisionReason.SETUP_ABSENT,
            ),
            _target_record(
                change=change,
                passed=target_passed,
                blocked=target_blocked,
            ),
        )

    extension_ok = (
        extension_atr <= Decimal(params["maximum_extension_atr"])
    )
    if change == REMOVE_VOLATILITY_EXTENSION:
        target_passed = extension_ok
        target_blocked = not extension_ok
    elif not extension_ok:
        return (
            StrategyDecision(
                context,
                StrategyAction.NO_TRADE,
                DecisionReason.SETUP_ABSENT,
            ),
            _target_record(change=change),
        )

    confirmation = False
    if len(context.snapshot.context) >= 2:
        previous_15m, latest_15m = context.snapshot.context[-2:]
        confirmation = (
            Decimal(latest_15m.close) > Decimal(latest_15m.open)
            and Decimal(latest_15m.close)
            > Decimal(previous_15m.close)
        )
    if change == REMOVE_CONFIRMATION:
        target_passed = confirmation
        target_blocked = not confirmation
    elif not confirmation:
        return (
            StrategyDecision(
                context,
                StrategyAction.NO_TRADE,
                DecisionReason.CONFIRMATION_FAILED,
            ),
            _target_record(
                change=change,
                passed=target_passed,
                blocked=target_blocked,
            ),
        )

    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        invalidation = Decimal(
            _plain(
                low
                - volatility.value
                * Decimal(params["stop_atr_fraction"])
            )
        )
    setup = _setup(
        close,
        invalidation,
        Decimal(params["reward_risk"]),
    )
    if setup is None:
        return (
            StrategyDecision(
                context,
                StrategyAction.NO_TRADE,
                DecisionReason.SETUP_ABSENT,
            ),
            _target_record(
                change=change,
                passed=target_passed,
                blocked=target_blocked,
            ),
        )
    return (
        StrategyDecision(
            context,
            StrategyAction.ENTER_LONG,
            DecisionReason.BREAKOUT_ENTRY,
            setup,
        ),
        _target_record(
            change=change,
            passed=target_passed,
            blocked=target_blocked,
        ),
    )


def _evaluate_experiment(
    experiment: Mapping[str, object],
    context: StrategyContext,
    *,
    in_position: bool,
    active_setup,
):
    changes = experiment["entry_changes"]
    change = changes[0] if changes else None
    strategy_id = experiment["strategy_id"]
    if strategy_id == "TREND_PULLBACK":
        return _evaluate_trend(
            context,
            in_position=in_position,
            active_setup=active_setup,
            change=change,
        )
    if strategy_id == "RANGE_BREAKOUT":
        return _evaluate_breakout(
            context,
            in_position=in_position,
            active_setup=active_setup,
            change=change,
        )
    raise HSLAblationError("HSL-003 strategy is not registered")


def _identity_for(strategy_id: str):
    if strategy_id == "TREND_PULLBACK":
        return TREND_PULLBACK_IDENTITY, TREND_PULLBACK_CONFIGURATION
    if strategy_id == "RANGE_BREAKOUT":
        return BREAKOUT_IDENTITY, BREAKOUT_CONFIGURATION
    raise HSLAblationError("HSL-003 strategy identity is invalid")


def _run_cell(
    *,
    corpus: controls.AdmittedControlCorpus,
    fold: Mapping[str, object],
    experiment: Mapping[str, object],
    symbol: str,
) -> dict[str, object]:
    _, _, evaluation_start, evaluation_end = hsl1._fold_times(fold)
    identity, configuration = _identity_for(
        str(experiment["strategy_id"])
    )
    try:
        dataset, dataset_sha = hsl1._dataset(
            corpus=corpus,
            symbol=symbol,
            evaluation_start_ms=evaluation_start,
            evaluation_end_ms=evaluation_end,
        )
    except hsl1.HSLImplementationError as exc:
        raise HSLAblationError(str(exc)) from None

    by_open = {item.open_time_ms: item for item in dataset.primary}
    if len(by_open) != len(dataset.primary):
        raise HSLAblationError("HSL-003 primary candles are duplicated")
    events = tuple(BacktestClock(dataset).events())
    if not events:
        raise HSLAblationError("HSL-003 fold has no decision events")
    analysis_primary = tuple(
        item
        for item in dataset.primary
        if evaluation_start <= item.open_time_ms < evaluation_end
    )
    if not analysis_primary:
        raise HSLAblationError("HSL-003 fold has no analysis candles")

    fill_engine = PaperFillEngine(symbol)
    ledger = PortfolioLedger(dataset.spec)
    active_setup = None
    open_trade_cash_delta: Decimal | None = None
    trade_pnls: list[Decimal] = []
    counts = {
        "decision": 0,
        "missing_fill": 0,
        "stale_snapshot": 0,
        "entry_signal": 0,
        "entry_gap_rejected": 0,
        "entry_fill": 0,
        "exit_fill": 0,
        "filter_pass": 0,
        "filter_block": 0,
    }

    initial = Decimal(CandidateFreeze().initial_equity_quote)
    peak = initial
    maximum_drawdown_fraction = Decimal(0)

    for decision_event in events:
        fill_candle = by_open.get(
            decision_event.eligible_fill_open_time_ms
        )
        if fill_candle is None:
            counts["missing_fill"] += 1
            continue
        if not fill_candle.is_closed:
            raise HSLAblationError("HSL-003 fill candle is not closed")
        if any(
            candle.close_time_ms >= decision_event.decision_time_ms
            for series in (
                decision_event.snapshot.primary,
                decision_event.snapshot.context,
                decision_event.snapshot.regime,
            )
            for candle in series
        ):
            raise HSLAblationError(
                "HSL-003 decision contains future data"
            )

        counts["decision"] += 1
        decision = None
        target = _target_record(change=None)
        if not replay._snapshot_is_fresh(decision_event.snapshot):
            counts["stale_snapshot"] += 1
            intent = PaperIntent(
                IntentAction.HOLD,
                decision_event.decision_time_ms,
            )
        else:
            context = StrategyContext(identity, decision_event.snapshot)
            decision, target = _evaluate_experiment(
                experiment,
                context,
                in_position=fill_engine.has_position,
                active_setup=active_setup,
            )
            if target["target_filter_passed"]:
                counts["filter_pass"] += 1
            if target["target_filter_blocked"]:
                counts["filter_block"] += 1

            if decision.action is StrategyAction.ENTER_LONG:
                counts["entry_signal"] += 1
                opened = Decimal(fill_candle.open)
                stop = Decimal(decision.setup.invalidation_price)
                target_price = Decimal(decision.setup.target_price)
                if not stop < opened < target_price:
                    counts["entry_gap_rejected"] += 1
                    intent = PaperIntent(
                        IntentAction.HOLD,
                        decision_event.decision_time_ms,
                    )
                else:
                    intent = PaperIntent(
                        IntentAction.ENTER_LONG,
                        decision_event.decision_time_ms,
                        RUNNER_QUANTITY,
                        decision.setup.invalidation_price,
                        decision.setup.target_price,
                    )
            elif decision.action is StrategyAction.EXIT_LONG:
                intent = PaperIntent(
                    IntentAction.EXIT_LONG,
                    decision_event.decision_time_ms,
                )
            else:
                intent = PaperIntent(
                    IntentAction.HOLD,
                    decision_event.decision_time_ms,
                )

        references = fill_engine.process(
            decision_event, intent, fill_candle
        )
        costed = tuple(
            apply_costs(item, dataset.spec) for item in references
        )
        if costed:
            ledger.apply_many(costed)

        for fill in costed:
            if fill.reference.action is IntentAction.ENTER_LONG:
                counts["entry_fill"] += 1
                if open_trade_cash_delta is not None:
                    raise HSLAblationError(
                        "HSL-003 overlapping trade accounting"
                    )
                open_trade_cash_delta = fill.cash_delta
            else:
                counts["exit_fill"] += 1
                if open_trade_cash_delta is None:
                    raise HSLAblationError(
                        "HSL-003 exit has no paired entry"
                    )
                with localcontext() as arithmetic:
                    arithmetic.prec = DECIMAL_PRECISION
                    pnl = open_trade_cash_delta + fill.cash_delta
                trade_pnls.append(pnl)
                open_trade_cash_delta = None

        if fill_engine.has_position:
            if (
                intent.action is IntentAction.ENTER_LONG
                and decision is not None
            ):
                active_setup = decision.setup
            elif active_setup is None:
                raise HSLAblationError(
                    "HSL-003 open position lost setup state"
                )
        else:
            active_setup = None

        snapshot = ledger.snapshot(fill_candle.open)
        peak, maximum_drawdown_fraction = hsl1._drawdown_update(
            snapshot.equity_quote,
            peak,
            maximum_drawdown_fraction,
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
        raise HSLAblationError(
            "HSL-003 closed-trade accounting disagrees with ledger"
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
    profit_factor, profit_factor_infinite = hsl1._profit_factor(
        gross_profit, gross_loss
    )

    return {
        "fold_id": fold["fold_id"],
        "symbol": symbol,
        "candidate_id": experiment["experiment_id"],
        "experiment_id": experiment["experiment_id"],
        "strategy_id": identity.strategy_id,
        "strategy_version": identity.version,
        "role": experiment["role"],
        "entry_changes": experiment["entry_changes"],
        "configuration_sha256": configuration.sha256,
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
        "filter_pass_count": counts["filter_pass"],
        "filter_block_count": counts["filter_block"],
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
        "open_position_at_fold_end": fill_engine.has_position,
        "terminal_position_forced_closed": False,
        "point_in_time_verified": True,
    }


def _aggregate(
    *,
    experiment: Mapping[str, object],
    cells: Sequence[Mapping[str, object]],
    gate: Mapping[str, object],
) -> dict[str, object]:
    candidate = {
        "candidate_id": experiment["experiment_id"],
        "strategy_id": experiment["strategy_id"],
        "strategy_version": experiment["strategy_version"],
        "role": experiment["role"],
    }
    try:
        result = hsl1._aggregate_candidate(
            candidate_record=candidate,
            cells=cells,
            gate=gate,
        )
    except hsl1.HSLImplementationError as exc:
        raise HSLAblationError(str(exc)) from None
    result["experiment_id"] = experiment["experiment_id"]
    result["entry_changes"] = experiment["entry_changes"]
    result["filter_pass_count"] = sum(
        int(item["filter_pass_count"]) for item in cells
    )
    result["filter_block_count"] = sum(
        int(item["filter_block_count"]) for item in cells
    )
    result["entry_signal_count"] = sum(
        int(item["entry_signal_count"]) for item in cells
    )
    result["entry_fill_count"] = sum(
        int(item["entry_fill_count"]) for item in cells
    )
    result["exit_fill_count"] = sum(
        int(item["exit_fill_count"]) for item in cells
    )
    return result


def _comparison(
    *,
    experiment: Mapping[str, object],
    summary: Mapping[str, object],
    control: Mapping[str, object],
    gate: Mapping[str, object],
) -> dict[str, object]:
    if experiment["role"] == "CONTROL":
        return {
            "experiment_id": experiment["experiment_id"],
            "strategy_id": experiment["strategy_id"],
            "control_experiment_id": experiment["experiment_id"],
            "status": "CONTROL",
            "failure_reasons": [],
            "automatic_strategy_mutation": False,
            "p10_evidence_effect": "NONE",
            "p11_locked": True,
            "live_authorized": False,
        }

    failures = list(
        summary["qualification"]["failure_reasons"]
    )
    summary_net = _number(
        summary["total_net_pnl_after_costs_quote"],
        "ablation net pnl",
    )
    control_net = _number(
        control["total_net_pnl_after_costs_quote"],
        "control net pnl",
    )
    summary_exp = (
        None
        if summary["expectancy_quote"] is None
        else _number(summary["expectancy_quote"], "ablation expectancy")
    )
    control_exp = (
        None
        if control["expectancy_quote"] is None
        else _number(control["expectancy_quote"], "control expectancy")
    )
    if (
        gate.get("require_net_pnl_above_control") is True
        and summary_net <= control_net
    ):
        failures.append("NET_PNL_DID_NOT_BEAT_CONTROL")
    if gate.get("require_expectancy_not_below_control") is True:
        if (
            summary_exp is None
            or control_exp is None
            or summary_exp < control_exp
        ):
            failures.append("EXPECTANCY_BELOW_CONTROL")

    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        net_delta = summary_net - control_net
        exp_delta = (
            None
            if summary_exp is None or control_exp is None
            else summary_exp - control_exp
        )
        dd_delta = (
            _number(
                summary["maximum_drawdown_fraction"],
                "ablation drawdown",
            )
            - _number(
                control["maximum_drawdown_fraction"],
                "control drawdown",
            )
        )

    deduped = list(dict.fromkeys(failures))
    return {
        "experiment_id": experiment["experiment_id"],
        "strategy_id": experiment["strategy_id"],
        "control_experiment_id": control["experiment_id"],
        "entry_changes": experiment["entry_changes"],
        "completed_trades_delta": (
            int(summary["completed_trades"])
            - int(control["completed_trades"])
        ),
        "net_pnl_after_costs_delta_quote": _plain(net_delta),
        "expectancy_delta_quote": _plain(exp_delta),
        "maximum_drawdown_delta_fraction": _plain(dd_delta),
        "entry_signal_delta": (
            int(summary["entry_signal_count"])
            - int(control["entry_signal_count"])
        ),
        "filter_pass_count": summary["filter_pass_count"],
        "filter_block_count": summary["filter_block_count"],
        "status": (
            "ABLATION_SUPPORTS_FUTURE_CHALLENGER"
            if not deduped
            else "ABLATION_NOT_SUPPORTED"
        ),
        "failure_reasons": deduped,
        "automatic_strategy_mutation": False,
        "p10_evidence_effect": "NONE",
        "p11_locked": True,
        "live_authorized": False,
    }


def run_entry_regime_ablation(
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
        raise HSLAblationError(str(exc)) from None

    cells: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    by_id: dict[str, dict[str, object]] = {}
    for experiment in protocol["experiments"]:
        experiment_cells = []
        for fold in parent["folds"]:
            for symbol in acq.ALLOWED_SYMBOLS:
                cell = _run_cell(
                    corpus=corpus,
                    fold=fold,
                    experiment=experiment,
                    symbol=symbol,
                )
                experiment_cells.append(cell)
                cells.append(cell)
        summary = _aggregate(
            experiment=experiment,
            cells=experiment_cells,
            gate=protocol["comparison_gate"],
        )
        summaries.append(summary)
        by_id[str(experiment["experiment_id"])] = summary

    comparisons = []
    for experiment in protocol["experiments"]:
        control_id = _CONTROL_BY_STRATEGY[
            str(experiment["strategy_id"])
        ]
        comparisons.append(
            _comparison(
                experiment=experiment,
                summary=by_id[str(experiment["experiment_id"])],
                control=by_id[control_id],
                gate=protocol["comparison_gate"],
            )
        )

    result: dict[str, object] = {
        "schema": "YATL_HSL_ENTRY_REGIME_ABLATION_RESULT",
        "schema_version": SCHEMA_VERSION,
        "implementation_id": IMPLEMENTATION_ID,
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
        "methodology": protocol["methodology"],
        "experiments": protocol["experiments"],
        "comparison_gate": protocol["comparison_gate"],
        "cells": cells,
        "experiment_summaries": summaries,
        "comparisons": comparisons,
        "historical_outcomes_used_for_strategy_selection": False,
        "post_hoc_combination_performed": False,
        "parameter_search_performed": False,
        "exit_logic_mutated": False,
        "protective_level_logic_mutated": False,
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
        / "entry-regime-ablation-v0.1.0"
        / f"hsl-003-{digest[:24]}.json"
    )


def run_and_write_entry_regime_ablation(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
    protocol_path: Path = DEFAULT_PROTOCOL_PATH,
) -> dict[str, object]:
    result = run_entry_regime_ablation(
        runtime_root=runtime_root,
        quality_manifest_relative_path=quality_manifest_relative_path,
        quality_manifest_file_sha256=quality_manifest_file_sha256,
        protocol_path=protocol_path,
    )
    payload = _canonical_json(result)
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise HSLAblationError("HSL-003 artifact exceeds bounded size")
    digest = _sha256(payload)
    try:
        relative = acq._write_immutable(
            runtime_root,
            _relative_path(digest),
            payload,
        )
    except acq.AcquisitionError as exc:
        raise HSLAblationError(str(exc)) from None
    return {
        "manifest_relative_path": relative,
        "manifest_file_sha256": digest,
        "result_sha256": result["result_sha256"],
        "comparisons": result["comparisons"],
        "research_only": True,
        "p4_policy_mutated": False,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=(
            "python -m "
            "research.historical_strategy_lab.entry_regime_ablation"
        ),
        description=(
            "YATL HSL-003 research-only single-filter ablations"
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
        result = run_and_write_entry_regime_ablation(
            runtime_root=args.runtime_root,
            quality_manifest_relative_path=args.quality_manifest,
            quality_manifest_file_sha256=args.quality_manifest_sha256,
            protocol_path=args.protocol,
        )
    except HSLAblationError as exc:
        print(
            json.dumps(
                {
                    "code": "HSL003_ABLATION_ERROR",
                    "reason": str(exc),
                    "research_only": True,
                    "p4_policy_mutated": False,
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
