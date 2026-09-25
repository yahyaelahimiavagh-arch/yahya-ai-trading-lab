"""HSL-001 deterministic historical walk-forward strategy lab.

Research-only. This module measures strategy edge on the already admitted
CRL Development corpus. It intentionally does not apply the P4/P10 risk veto:
HSL-001 isolates signal/exit quality with fixed paper quantity and accepted
fee/slippage before any later risk-overlay research. It has no network,
credentials, account, order, notification, AI, or P10 write capability.
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
    BacktestSpec,
    IntentAction,
    PaperFillEngine,
    PaperIntent,
    PortfolioLedger,
    apply_costs,
)
from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.data import INTERVAL_MILLISECONDS
from yatl.strategy import (
    BREAKOUT_CONFIGURATION,
    BREAKOUT_IDENTITY,
    TREND_PULLBACK_CONFIGURATION,
    TREND_PULLBACK_IDENTITY,
    StrategyAction,
    StrategyContext,
    evaluate_breakout,
    evaluate_trend_pullback,
)
from yatl.strategy.adapter import FIXED_RESEARCH_QUANTITY
from yatl.validation.paper_runner import RUNNER_QUANTITY
from yatl.validation.registration import CandidateFreeze

from research.crisis_lab import acquisition as acq
from research.crisis_lab import controls, replay


IMPLEMENTATION_ID = "HSL-001-WALK-FORWARD/0.1.0"
SCHEMA_VERSION = "0.1.0"
DEFAULT_PROTOCOL_PATH = Path(
    "docs/research/historical-strategy-lab/"
    "HSL-001-WALK-FORWARD-PROTOCOL-v0.1.0.json"
)
MAX_PROTOCOL_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024

_CANDIDATES = {
    "TREND_PULLBACK": {
        "identity": TREND_PULLBACK_IDENTITY,
        "configuration": TREND_PULLBACK_CONFIGURATION,
        "evaluator": evaluate_trend_pullback,
    },
    "RANGE_BREAKOUT": {
        "identity": BREAKOUT_IDENTITY,
        "configuration": BREAKOUT_CONFIGURATION,
        "evaluator": evaluate_breakout,
    },
}


class HSLImplementationError(RuntimeError):
    """Historical Strategy Lab violated a frozen research boundary."""


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
        raise HSLImplementationError("HSL arithmetic is not finite")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _number(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception:
        raise HSLImplementationError(f"{label} is not numeric") from None
    if not result.is_finite():
        raise HSLImplementationError(f"{label} is not finite")
    return result


def load_protocol(
    path: Path = DEFAULT_PROTOCOL_PATH,
) -> tuple[dict[str, object], str]:
    try:
        target = acq.assert_safe_runtime_path(path)
    except acq.AcquisitionError as exc:
        raise HSLImplementationError(str(exc)) from None
    if target.is_symlink():
        raise HSLImplementationError("symlink HSL protocol is forbidden")
    try:
        payload = target.read_bytes()
    except OSError:
        raise HSLImplementationError("cannot read HSL protocol") from None
    if not payload or len(payload) > MAX_PROTOCOL_BYTES:
        raise HSLImplementationError("HSL protocol size is invalid")
    try:
        protocol = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HSLImplementationError(
            "HSL protocol is not canonical UTF-8 JSON"
        ) from None
    if not isinstance(protocol, dict):
        raise HSLImplementationError("HSL protocol must be an object")
    if (
        protocol.get("schema") != "YATL_HSL_WALK_FORWARD_PROTOCOL"
        or protocol.get("version") != SCHEMA_VERSION
        or protocol.get("research_only") is not True
        or protocol.get("paper_only") is not True
        or protocol.get("p10_untouched") is not True
        or protocol.get("p11_locked") is not True
        or protocol.get("live_master_lock") != "OFF"
        or protocol.get("trade_permission") is not False
        or protocol.get("order_endpoint") is not False
        or protocol.get("ai_direct_execution") is not False
        or protocol.get("source_corpus_id") != controls.CONTROL_CORPUS_ID
    ):
        raise HSLImplementationError("HSL protocol invariants are invalid")

    methodology = protocol.get("methodology")
    candidates = protocol.get("candidates")
    folds = protocol.get("folds")
    gate = protocol.get("qualification_gate")
    if (
        not isinstance(methodology, dict)
        or not isinstance(candidates, list)
        or not isinstance(folds, list)
        or not isinstance(gate, dict)
        or len(candidates) != 2
        or len(folds) != 5
    ):
        raise HSLImplementationError("HSL protocol scope is incomplete")

    frozen = CandidateFreeze()
    if (
        methodology.get("p4_risk_veto_applied") is not False
        or methodology.get("state_reset_at_each_evaluation_fold") is not True
        or methodology.get("market_history_available_point_in_time") is not True
        or methodology.get("fixed_quantity") != RUNNER_QUANTITY
        or RUNNER_QUANTITY != FIXED_RESEARCH_QUANTITY
        or methodology.get("fee_bps") != str(frozen.fee_bps)
        or methodology.get("slippage_bps") != str(frozen.slippage_bps)
        or methodology.get("execution")
        != "NEXT_PRIMARY_OPEN_LONG_ONLY_SPOT"
    ):
        raise HSLImplementationError(
            "HSL execution semantics differ from registration"
        )

    expected = {
        "TREND_PULLBACK": (
            "1.0.0",
            dict(TREND_PULLBACK_CONFIGURATION.values),
        ),
        "RANGE_BREAKOUT": (
            "1.0.0",
            dict(BREAKOUT_CONFIGURATION.values),
        ),
    }
    seen: set[str] = set()
    for record in candidates:
        if not isinstance(record, dict):
            raise HSLImplementationError("HSL candidate is invalid")
        strategy_id = record.get("strategy_id")
        version = record.get("strategy_version")
        parameters = record.get("parameters")
        if (
            strategy_id not in expected
            or strategy_id in seen
            or version != expected[strategy_id][0]
            or parameters != expected[strategy_id][1]
        ):
            raise HSLImplementationError(
                "HSL candidate registration differs from code"
            )
        seen.add(str(strategy_id))
    if seen != set(expected):
        raise HSLImplementationError("HSL candidate set is incomplete")

    previous_end: int | None = None
    for index, fold in enumerate(folds):
        if not isinstance(fold, dict):
            raise HSLImplementationError("HSL fold is invalid")
        if fold.get("fold_id") != f"HSL-F{index + 1:03d}":
            raise HSLImplementationError("HSL fold identity is invalid")
        try:
            train_start = acq._iso_to_ms(fold["training_start_utc"])
            train_end = acq._iso_to_ms(
                fold["training_end_exclusive_utc"]
            )
            eval_start = acq._iso_to_ms(fold["evaluation_start_utc"])
            eval_end = acq._iso_to_ms(
                fold["evaluation_end_exclusive_utc"]
            )
        except (KeyError, TypeError, acq.AcquisitionError):
            raise HSLImplementationError(
                "HSL fold timestamps are invalid"
            ) from None
        hour = INTERVAL_MILLISECONDS["1h"]
        if (
            not train_start < train_end == eval_start < eval_end
            or any(
                value % hour
                for value in (
                    train_start,
                    train_end,
                    eval_start,
                    eval_end,
                )
            )
            or (
                previous_end is not None
                and previous_end != eval_start
            )
        ):
            raise HSLImplementationError(
                "HSL folds are not sequential and aligned"
            )
        previous_end = eval_end

    return protocol, _sha256(payload)


def _fold_times(
    fold: Mapping[str, object],
) -> tuple[int, int, int, int]:
    try:
        return (
            acq._iso_to_ms(fold["training_start_utc"]),
            acq._iso_to_ms(fold["training_end_exclusive_utc"]),
            acq._iso_to_ms(fold["evaluation_start_utc"]),
            acq._iso_to_ms(fold["evaluation_end_exclusive_utc"]),
        )
    except (KeyError, TypeError, acq.AcquisitionError):
        raise HSLImplementationError("HSL fold timestamps are invalid") from None


def _dataset(
    *,
    corpus: controls.AdmittedControlCorpus,
    symbol: str,
    evaluation_start_ms: int,
    evaluation_end_ms: int,
):
    frozen = CandidateFreeze()
    values = {
        interval: corpus.datasets[(symbol, interval)]
        for interval in acq.ALLOWED_INTERVALS
    }
    warmup_ready = (
        values["4h"][0].open_time_ms
        + replay.REGIME_WARMUP_BARS * INTERVAL_MILLISECONDS["4h"]
    )
    common_end = min(
        rows[-1].open_time_ms + INTERVAL_MILLISECONDS[interval]
        for interval, rows in values.items()
    )
    common_end = (
        common_end // INTERVAL_MILLISECONDS["1h"]
    ) * INTERVAL_MILLISECONDS["1h"]
    if evaluation_start_ms < warmup_ready:
        raise HSLImplementationError("HSL fold lacks strategy warmup")
    if evaluation_end_ms > common_end:
        raise HSLImplementationError("HSL fold exceeds admitted corpus")

    spec = BacktestSpec(
        symbol,
        evaluation_start_ms,
        evaluation_end_ms,
        initial_cash=frozen.initial_equity_quote,
        fee_bps=str(frozen.fee_bps),
        slippage_bps=str(frozen.slippage_bps),
    )
    dataset = replay.CrisisLabAcceptedBacktestDataset(
        spec=spec,
        manifest_generated_at_ms=corpus.retrieved_at_ms,
        primary=values["1h"],
        context=values["15m"],
        regime=values["4h"],
    )
    return dataset, replay._dataset_digest(values)


def _drawdown_update(
    equity: Decimal,
    peak: Decimal,
    maximum_fraction: Decimal,
) -> tuple[Decimal, Decimal]:
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        peak = max(peak, equity)
        fraction = (peak - equity) / peak
    return peak, max(maximum_fraction, fraction)


def _profit_factor(
    gross_profit: Decimal,
    gross_loss: Decimal,
) -> tuple[str | None, bool]:
    if gross_loss == 0:
        return None, gross_profit > 0
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        value = gross_profit / gross_loss
    return _plain(value), False


def _run_cell(
    *,
    corpus: controls.AdmittedControlCorpus,
    fold: Mapping[str, object],
    candidate_record: Mapping[str, object],
) -> dict[str, object]:
    _, _, evaluation_start, evaluation_end = _fold_times(fold)
    strategy_id = candidate_record["strategy_id"]
    registry = _CANDIDATES.get(str(strategy_id))
    if registry is None:
        raise HSLImplementationError("HSL candidate is not registered")
    identity = registry["identity"]
    evaluator = registry["evaluator"]
    symbol = str(candidate_record["_symbol"])

    dataset, dataset_sha = _dataset(
        corpus=corpus,
        symbol=symbol,
        evaluation_start_ms=evaluation_start,
        evaluation_end_ms=evaluation_end,
    )
    by_open = {
        item.open_time_ms: item for item in dataset.primary
    }
    if len(by_open) != len(dataset.primary):
        raise HSLImplementationError("HSL primary candles are duplicated")

    events = tuple(BacktestClock(dataset).events())
    if not events:
        raise HSLImplementationError("HSL fold has no decision events")
    analysis_primary = tuple(
        item
        for item in dataset.primary
        if evaluation_start <= item.open_time_ms < evaluation_end
    )
    if not analysis_primary:
        raise HSLImplementationError("HSL fold has no analysis candles")

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
    }

    initial = Decimal(CandidateFreeze().initial_equity_quote)
    peak = initial
    maximum_drawdown_fraction = Decimal(0)

    for decision_event in events:
        counts["decision"] += 1
        fill_candle = by_open.get(
            decision_event.eligible_fill_open_time_ms
        )
        if fill_candle is None:
            counts["missing_fill"] += 1
            continue
        if not fill_candle.is_closed:
            raise HSLImplementationError(
                "HSL fill candle is not closed"
            )
        if any(
            candle.close_time_ms >= decision_event.decision_time_ms
            for series in (
                decision_event.snapshot.primary,
                decision_event.snapshot.context,
                decision_event.snapshot.regime,
            )
            for candle in series
        ):
            raise HSLImplementationError(
                "HSL decision contains future data"
            )

        decision = None
        if not replay._snapshot_is_fresh(decision_event.snapshot):
            counts["stale_snapshot"] += 1
            intent = PaperIntent(
                IntentAction.HOLD,
                decision_event.decision_time_ms,
            )
        else:
            context = StrategyContext(identity, decision_event.snapshot)
            decision = evaluator(
                context,
                in_position=fill_engine.has_position,
                active_setup=active_setup,
            )
            if decision.action is StrategyAction.ENTER_LONG:
                counts["entry_signal"] += 1
                opened = Decimal(fill_candle.open)
                stop = Decimal(decision.setup.invalidation_price)
                target = Decimal(decision.setup.target_price)
                if not stop < opened < target:
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
                    raise HSLImplementationError(
                        "HSL trade accounting overlapped positions"
                    )
                open_trade_cash_delta = fill.cash_delta
            else:
                counts["exit_fill"] += 1
                if open_trade_cash_delta is None:
                    raise HSLImplementationError(
                        "HSL exit has no paired entry"
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
                raise HSLImplementationError(
                    "HSL open position lost setup state"
                )
        else:
            active_setup = None

        snapshot = ledger.snapshot(fill_candle.open)
        peak, maximum_drawdown_fraction = _drawdown_update(
            snapshot.equity_quote,
            peak,
            maximum_drawdown_fraction,
        )

    final_mark = analysis_primary[-1].close
    final_snapshot = ledger.snapshot(final_mark)
    peak, maximum_drawdown_fraction = _drawdown_update(
        final_snapshot.equity_quote,
        peak,
        maximum_drawdown_fraction,
    )

    realized = sum(trade_pnls, Decimal(0))
    if realized != final_snapshot.realized_pnl_quote:
        raise HSLImplementationError(
            "HSL closed-trade accounting disagrees with ledger"
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
        expectancy = (
            realized / completed if completed else None
        )
        win_rate = (
            Decimal(len(wins)) / completed if completed else None
        )
        largest_positive = max(wins) if wins else Decimal(0)
        largest_share = (
            largest_positive / gross_profit
            if gross_profit > 0
            else None
        )
    profit_factor, profit_factor_infinite = _profit_factor(
        gross_profit, gross_loss
    )

    return {
        "fold_id": fold["fold_id"],
        "symbol": symbol,
        "candidate_id": candidate_record["candidate_id"],
        "strategy_id": identity.strategy_id,
        "strategy_version": identity.version,
        "configuration_sha256": registry["configuration"].sha256,
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
        "open_position_at_fold_end": fill_engine.has_position,
        "terminal_position_forced_closed": False,
        "point_in_time_verified": True,
    }


def _aggregate_candidate(
    *,
    candidate_record: Mapping[str, object],
    cells: Sequence[Mapping[str, object]],
    gate: Mapping[str, object],
) -> dict[str, object]:
    if len(cells) != 10:
        raise HSLImplementationError(
            "HSL candidate must have five folds for both symbols"
        )
    completed = sum(int(item["completed_trades"]) for item in cells)
    wins = sum(int(item["wins"]) for item in cells)
    losses = sum(int(item["losses"]) for item in cells)
    gross_profit = sum(
        (_number(item["gross_profit_quote"], "gross profit") for item in cells),
        Decimal(0),
    )
    gross_loss = sum(
        (_number(item["gross_loss_quote"], "gross loss") for item in cells),
        Decimal(0),
    )
    total_net = sum(
        (
            _number(item["net_pnl_after_costs_quote"], "net pnl")
            for item in cells
        ),
        Decimal(0),
    )
    realized = sum(
        (
            _number(
                item["realized_closed_trade_pnl_quote"],
                "realized pnl",
            )
            for item in cells
        ),
        Decimal(0),
    )
    total_cost = sum(
        (
            _number(item["executed_total_cost_quote"], "total cost")
            for item in cells
        ),
        Decimal(0),
    )
    maximum_drawdown = max(
        _number(item["maximum_drawdown_fraction"], "drawdown")
        for item in cells
    )
    positive_cells = sum(
        _number(item["net_pnl_after_costs_quote"], "cell pnl") > 0
        for item in cells
    )
    largest_positive = max(
        _number(
            item["largest_positive_trade_quote"],
            "largest positive trade",
        )
        for item in cells
    )
    per_symbol = {
        symbol: sum(
            int(item["completed_trades"])
            for item in cells
            if item["symbol"] == symbol
        )
        for symbol in acq.ALLOWED_SYMBOLS
    }
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        expectancy = realized / completed if completed else None
        win_rate = Decimal(wins) / completed if completed else None
        positive_fraction = Decimal(positive_cells) / len(cells)
        largest_share = (
            largest_positive / gross_profit if gross_profit > 0 else None
        )
    profit_factor, profit_factor_infinite = _profit_factor(
        gross_profit, gross_loss
    )

    failures: list[str] = []
    minimum_total = int(gate["minimum_completed_trades_total"])
    minimum_symbol = int(gate["minimum_completed_trades_per_symbol"])
    if completed < minimum_total:
        failures.append("MINIMUM_COMPLETED_TRADES_TOTAL_NOT_MET")
    if any(value < minimum_symbol for value in per_symbol.values()):
        failures.append("MINIMUM_COMPLETED_TRADES_PER_SYMBOL_NOT_MET")
    if (
        gate.get("require_positive_total_net_pnl") is True
        and total_net <= 0
    ):
        failures.append("TOTAL_NET_PNL_NOT_POSITIVE")
    if (
        gate.get("require_positive_expectancy") is True
        and (expectancy is None or expectancy <= 0)
    ):
        failures.append("EXPECTANCY_NOT_POSITIVE")
    minimum_pf = _number(gate["minimum_profit_factor"], "minimum profit factor")
    if not profit_factor_infinite:
        if profit_factor is None or _number(
            profit_factor, "profit factor"
        ) < minimum_pf:
            failures.append("PROFIT_FACTOR_GATE_FAILED")
    minimum_positive = _number(
        gate["minimum_positive_oos_cell_fraction"],
        "positive cell fraction gate",
    )
    if positive_fraction < minimum_positive:
        failures.append("POSITIVE_OOS_CELL_FRACTION_GATE_FAILED")
    maximum_share = _number(
        gate["maximum_single_trade_share_of_positive_pnl"],
        "single-trade share gate",
    )
    if largest_share is None or largest_share > maximum_share:
        failures.append("OUTLIER_DEPENDENCE_GATE_FAILED")
    maximum_dd = _number(
        gate["maximum_drawdown_fraction"],
        "maximum drawdown gate",
    )
    if maximum_drawdown > maximum_dd:
        failures.append("MAXIMUM_DRAWDOWN_GATE_FAILED")

    return {
        "candidate_id": candidate_record["candidate_id"],
        "strategy_id": candidate_record["strategy_id"],
        "strategy_version": candidate_record["strategy_version"],
        "role": candidate_record["role"],
        "cell_count": len(cells),
        "completed_trades": completed,
        "completed_trades_by_symbol": per_symbol,
        "wins": wins,
        "losses": losses,
        "win_rate": _plain(win_rate),
        "expectancy_quote": _plain(expectancy),
        "gross_profit_quote": _plain(gross_profit),
        "gross_loss_quote": _plain(gross_loss),
        "profit_factor": profit_factor,
        "profit_factor_infinite": profit_factor_infinite,
        "total_net_pnl_after_costs_quote": _plain(total_net),
        "realized_closed_trade_pnl_quote": _plain(realized),
        "executed_total_cost_quote": _plain(total_cost),
        "positive_oos_cells": positive_cells,
        "positive_oos_cell_fraction": _plain(positive_fraction),
        "largest_positive_trade_quote": _plain(largest_positive),
        "largest_trade_profit_share": _plain(largest_share),
        "maximum_drawdown_fraction": _plain(maximum_drawdown),
        "qualification": {
            "status": (
                "QUALIFIED_HSL_RESEARCH"
                if not failures
                else "NOT_QUALIFIED_HSL_RESEARCH"
            ),
            "failure_reasons": failures,
            "not_p10_p11_or_live_approval": True,
        },
    }


def run_walk_forward(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
    protocol_path: Path = DEFAULT_PROTOCOL_PATH,
) -> dict[str, object]:
    protocol, protocol_sha = load_protocol(protocol_path)
    try:
        corpus = controls._load_control_corpus(
            runtime_root=runtime_root,
            quality_manifest_relative_path=quality_manifest_relative_path,
            quality_manifest_file_sha256=quality_manifest_file_sha256,
        )
    except controls.ControlError as exc:
        raise HSLImplementationError(str(exc)) from None

    candidates = protocol["candidates"]
    folds = protocol["folds"]
    gate = protocol["qualification_gate"]

    all_cells: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for candidate in candidates:
        candidate_cells: list[dict[str, object]] = []
        for fold in folds:
            for symbol in acq.ALLOWED_SYMBOLS:
                scoped = dict(candidate)
                scoped["_symbol"] = symbol
                cell = _run_cell(
                    corpus=corpus,
                    fold=fold,
                    candidate_record=scoped,
                )
                candidate_cells.append(cell)
                all_cells.append(cell)
        summaries.append(
            _aggregate_candidate(
                candidate_record=candidate,
                cells=candidate_cells,
                gate=gate,
            )
        )

    result: dict[str, object] = {
        "schema": "YATL_HSL_WALK_FORWARD_RESULT",
        "schema_version": SCHEMA_VERSION,
        "implementation_id": IMPLEMENTATION_ID,
        "protocol_relative_path": protocol_path.as_posix(),
        "protocol_sha256": protocol_sha,
        "source_corpus_id": corpus.event_id,
        "input_quality_manifest_relative_path": (
            corpus.quality_manifest_relative_path
        ),
        "input_quality_manifest_file_sha256": (
            corpus.quality_manifest_file_sha256
        ),
        "methodology": protocol["methodology"],
        "qualification_gate": gate,
        "cells": all_cells,
        "candidate_summaries": summaries,
        "historical_outcomes_used_for_configuration_selection": False,
        "future_path_used_for_configuration_selection": False,
        "research_only": True,
        "paper_only": True,
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
        / "walk-forward-v0.1.0"
        / f"hsl-001-{digest[:24]}.json"
    )


def run_and_write_walk_forward(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
    protocol_path: Path = DEFAULT_PROTOCOL_PATH,
) -> dict[str, object]:
    result = run_walk_forward(
        runtime_root=runtime_root,
        quality_manifest_relative_path=quality_manifest_relative_path,
        quality_manifest_file_sha256=quality_manifest_file_sha256,
        protocol_path=protocol_path,
    )
    payload = _canonical_json(result)
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise HSLImplementationError("HSL artifact exceeds bounded size")
    digest = _sha256(payload)
    try:
        relative = acq._write_immutable(
            runtime_root,
            _relative_path(digest),
            payload,
        )
    except acq.AcquisitionError as exc:
        raise HSLImplementationError(str(exc)) from None
    return {
        "manifest_relative_path": relative,
        "manifest_file_sha256": digest,
        "result_sha256": result["result_sha256"],
        "candidate_summaries": [
            {
                "candidate_id": item["candidate_id"],
                "strategy_id": item["strategy_id"],
                "completed_trades": item["completed_trades"],
                "total_net_pnl_after_costs_quote": item[
                    "total_net_pnl_after_costs_quote"
                ],
                "profit_factor": item["profit_factor"],
                "profit_factor_infinite": item[
                    "profit_factor_infinite"
                ],
                "qualification": item["qualification"],
            }
            for item in result["candidate_summaries"]
        ],
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research.historical_strategy_lab",
        description=(
            "YATL HSL-001 historical walk-forward strategy lab"
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
        result = run_and_write_walk_forward(
            runtime_root=args.runtime_root,
            quality_manifest_relative_path=args.quality_manifest,
            quality_manifest_file_sha256=args.quality_manifest_sha256,
            protocol_path=args.protocol,
        )
    except HSLImplementationError as exc:
        print(
            json.dumps(
                {
                    "code": "HSL001_WALK_FORWARD_ERROR",
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
