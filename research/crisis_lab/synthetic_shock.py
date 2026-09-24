"""CRL-006A deterministic immediate open-position shock runtime.

Research-only. The runner consumes a preregistered CRL-005 selected entry state,
reconstructs the next point-in-time Strategy snapshot from the admitted
Development corpus, and applies a synthetic flat gap candle. The real next
primary candle is never used to construct the shock.

This phase measures only immediate mechanics. Kill-switch observation, delayed
zero-exposure, re-entry, whipsaw and recovery belong to CRL-006B.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Mapping, Sequence

from yatl.backtest import (
    BacktestLoadError,
    BacktestSpec,
    CostModelError,
    FillModelError,
    FillReason,
    FillReference,
    IntentAction,
    apply_costs,
)
from yatl.backtest.costs import BASIS_POINTS, DECIMAL_PRECISION
from yatl.data import Candle, INTERVAL_MILLISECONDS
from yatl.strategy import (
    LongSetup,
    StrategyAction,
    StrategyContext,
    StrategyContractError,
    TREND_PULLBACK_IDENTITY,
    TrendStrategyError,
    evaluate_trend_pullback,
)
from yatl.validation.paper_runner import RUNNER_QUANTITY, _fill_record
from yatl.validation.registration import CandidateFreeze

from . import acquisition as acq
from . import controls
from . import replay


IMPLEMENTATION_ID = "CRL-006A/0.1.0"
SCHEMA_VERSION = "0.1.0"
DEFAULT_REGISTRY_PATH = Path(
    "docs/research/crisis-lab/SYNTHETIC-SHOCK-REGISTRY-v0.1.0.json"
)
MAX_REGISTRY_BYTES = 2 * 1024 * 1024
MAX_RESULT_BYTES = 8 * 1024 * 1024
PRIMARY_MS = INTERVAL_MILLISECONDS["1h"]


class ShockError(RuntimeError):
    """CRL-006A immediate shock replay failed closed."""


def _json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _canonical_json(value: object) -> bytes:
    return (_json(value) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _plain(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ShockError("shock arithmetic is not finite")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def load_registry(
    path: Path = DEFAULT_REGISTRY_PATH,
) -> tuple[dict[str, object], str]:
    try:
        target = acq.assert_safe_runtime_path(path)
    except acq.AcquisitionError as exc:
        raise ShockError(str(exc)) from None
    if target.is_symlink():
        raise ShockError("symlink shock registry is forbidden")
    try:
        payload = target.read_bytes()
    except OSError:
        raise ShockError("cannot read synthetic shock registry") from None
    if not payload or len(payload) > MAX_REGISTRY_BYTES:
        raise ShockError("synthetic shock registry size is invalid")
    try:
        registry = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ShockError("synthetic shock registry is not UTF-8 JSON") from None
    if not isinstance(registry, dict):
        raise ShockError("synthetic shock registry must be an object")
    if (
        registry.get("schema")
        != "YATL_CRL_SYNTHETIC_SHOCK_REGISTRY"
        or registry.get("schema_version") != SCHEMA_VERSION
        or registry.get("track_id")
        != "SYNTHETIC_OPEN_POSITION_SHOCK_V1"
        or registry.get("status")
        != "PREREGISTERED_BEFORE_SYNTHETIC_OUTCOMES"
        or registry.get("research_only") is not True
        or registry.get("p10_write_allowed") is not False
        or registry.get("p11_locked") is not True
    ):
        raise ShockError("synthetic shock registry invariants are invalid")

    source = registry.get("source_state")
    phase = registry.get("phase_006a_immediate_shock")
    matrix = registry.get("matrix")
    evidence = registry.get("evidence_policy")
    safety = registry.get("safety")
    if not all(
        isinstance(item, dict)
        for item in (source, phase, matrix, evidence, safety)
    ):
        raise ShockError("synthetic shock registry sections are incomplete")
    if (
        source.get("source")
        != "CRL-005_STRATEGY_ACTIVE_SELECTED_EPISODE"
        or source.get("confirmed_open_position_required") is not True
        or source.get("outcome_selected") is not False
        or source.get("future_next_candle_used_to_construct_shock")
        is not False
        or source.get("shock_anchor_policy")
        != "ENTRY_CANDLE_CLOSE_AFTER_SAME_CANDLE_PROTECTIVE_PROCESSING"
    ):
        raise ShockError("shock source-state policy is invalid")
    if (
        phase.get("decision_time_policy")
        != "NEXT_PRIMARY_DECISION_AFTER_ENTRY_CANDLE"
        or phase.get("strategy_snapshot_policy")
        != "SOURCE_CORPUS_ONLY_THROUGH_ENTRY_CANDLE"
        or phase.get("strategy_receives_scenario_label") is not False
        or phase.get("active_setup_preserved") is not True
        or phase.get("shock_bar_ohlc_policy")
        != "open=high=low=close=synthetic_open"
        or phase.get("fee_policy")
        != "FROZEN_CANDIDATE_FEE_BPS_UNCHANGED"
    ):
        raise ShockError("CRL-006A phase policy is invalid")

    scenarios = matrix.get("scenarios")
    if (
        matrix.get("adverse_gap_bps") != [500, 1000, 2000]
        or matrix.get("slippage_multipliers") != [1, 2, 5]
        or matrix.get("scenario_count") != 9
        or not isinstance(scenarios, list)
        or len(scenarios) != 9
    ):
        raise ShockError("synthetic shock matrix is not frozen to nine")
    expected = {
        (gap, multiplier)
        for gap in (500, 1000, 2000)
        for multiplier in (1, 2, 5)
    }
    actual = set()
    ids = set()
    for item in scenarios:
        if not isinstance(item, dict):
            raise ShockError("synthetic shock scenario is invalid")
        scenario_id = item.get("scenario_id")
        pair = (
            item.get("adverse_gap_bps"),
            item.get("slippage_multiplier"),
        )
        if (
            not isinstance(scenario_id, str)
            or scenario_id in ids
            or pair not in expected
            or item.get("fee_multiplier") != 1
            or item.get("shock_bar_policy")
            != "FLAT_AT_SYNTHETIC_GAP_OPEN"
        ):
            raise ShockError("synthetic shock scenario identity is invalid")
        ids.add(scenario_id)
        actual.add(pair)
    if actual != expected or len(ids) != 9:
        raise ShockError("synthetic shock matrix Cartesian product changed")
    if (
        evidence.get("label") != "SYNTHETIC"
        or evidence.get("pool_with_historical_returns") is not False
        or evidence.get("pool_with_p10_forward_evidence") is not False
        or evidence.get("negative_results_retained") is not True
        or evidence.get("deterministic_two_run_equality_required")
        is not True
        or safety.get("p10_read") is not False
        or safety.get("p10_write_allowed") is not False
        or safety.get("p10_evidence_effect") != "NONE"
        or safety.get("trade_permission") is not False
        or safety.get("order_endpoint") is not False
        or safety.get("quantity_authority") is not False
        or safety.get("risk_authorization_mutation") is not False
        or safety.get("ai_direct_execution") is not False
        or safety.get("p11_locked") is not True
    ):
        raise ShockError("synthetic evidence isolation policy is invalid")
    return registry, _sha256(payload)


def _load_active_diagnostic(
    *,
    runtime_root: Path,
    relative_path: str,
    file_sha256: str,
) -> dict[str, object]:
    try:
        root = replay._safe_root(runtime_root)
        active = replay._read_bound_json(
            root,
            relative=relative_path,
            sha256=file_sha256,
            prefix="strategy-active-",
            label="strategy-active diagnostic",
        )
    except replay.ReplayError as exc:
        raise ShockError(str(exc)) from None
    if (
        active.get("schema")
        != "YATL_CRL_STRATEGY_ACTIVE_DIAGNOSTIC"
        or active.get("schema_version") != "0.1.0"
        or active.get("source_corpus_id")
        != controls.CONTROL_CORPUS_ID
        or active.get("research_only") is not True
        or active.get("p10_read") is not False
        or active.get("p10_write_allowed") is not False
        or active.get("p10_evidence_effect") != "NONE"
        or active.get("trade_permission") is not False
        or active.get("order_endpoint") is not False
        or active.get("ai_direct_execution") is not False
        or active.get("p11_locked") is not True
        or active.get("future_outcomes_used_for_selection") is not False
        or active.get("historical_pnl_used_for_selection") is not False
    ):
        raise ShockError("strategy-active diagnostic is not admissible")
    selection = active.get("selection")
    candidate = active.get("candidate")
    episodes = active.get("selected_episodes")
    if (
        not isinstance(selection, dict)
        or selection.get("outcome_selected") is not False
        or selection.get("future_path_selected") is not False
        or selection.get("confirmed_open_position_required") is not True
        or not isinstance(candidate, dict)
        or candidate.get("candidate_sha256")
        != CandidateFreeze().candidate_sha256
        or not isinstance(episodes, list)
        or selection.get("selected_count") != len(episodes)
        or not episodes
    ):
        raise ShockError(
            "strategy-active selected source episodes are invalid"
        )
    bound = dict(active)
    result_sha = bound.pop("result_sha256", None)
    if (
        not isinstance(result_sha, str)
        or result_sha != _sha256(_canonical_json(bound))
    ):
        raise ShockError("strategy-active result digest binding changed")
    return active


def _load_corpus_from_active(
    *,
    runtime_root: Path,
    active: Mapping[str, object],
) -> controls.AdmittedControlCorpus:
    relative = active.get("input_quality_manifest_relative_path")
    digest = active.get("input_quality_manifest_file_sha256")
    if not isinstance(relative, str) or not isinstance(digest, str):
        raise ShockError("active diagnostic quality binding is missing")
    try:
        return controls._load_control_corpus(
            runtime_root=runtime_root,
            quality_manifest_relative_path=relative,
            quality_manifest_file_sha256=digest,
        )
    except controls.ControlError as exc:
        raise ShockError(str(exc)) from None


def _episode_identity(episode: Mapping[str, object]) -> str:
    payload = {
        "decision_time_ms": episode.get("decision_time_ms"),
        "fill_time_ms": episode.get("fill_time_ms"),
        "symbol": episode.get("symbol"),
        "context_sha256": episode.get("context_sha256"),
        "entry_fill": episode.get("entry_fill"),
        "entry_candle": episode.get("entry_candle"),
    }
    return _sha256(_canonical_json(payload))


def _validate_episode(
    episode: Mapping[str, object],
) -> tuple[str, Candle, LongSetup, dict[str, object]]:
    if not isinstance(episode, Mapping):
        raise ShockError("source episode is invalid")
    symbol = episode.get("symbol")
    decision_time = episode.get("decision_time_ms")
    fill_time = episode.get("fill_time_ms")
    context_sha = episode.get("context_sha256")
    setup_record = episode.get("active_setup")
    portfolio = episode.get("portfolio_after_entry")
    entry_fill = episode.get("entry_fill")
    entry_candle_record = episode.get("entry_candle")
    confirmed = episode.get("source_state_confirmed_at_ms")
    if (
        symbol not in acq.ALLOWED_SYMBOLS
        or type(decision_time) is not int
        or type(fill_time) is not int
        or fill_time != decision_time
        or not isinstance(context_sha, str)
        or len(context_sha) != 64
        or not isinstance(setup_record, dict)
        or not isinstance(portfolio, dict)
        or not isinstance(entry_fill, dict)
        or not isinstance(entry_candle_record, dict)
        or type(confirmed) is not int
    ):
        raise ShockError("source episode identity is incomplete")
    try:
        setup = LongSetup(
            setup_record["reference_price"],
            setup_record["invalidation_price"],
            setup_record["target_price"],
        )
        entry_candle = Candle(**entry_candle_record)
    except (
        KeyError,
        StrategyContractError,
        TypeError,
        ValueError,
    ):
        raise ShockError("source setup or entry candle is invalid") from None
    if (
        entry_candle.symbol != symbol
        or entry_candle.interval != "1h"
        or entry_candle.open_time_ms != fill_time
        or entry_candle.close_time_ms != fill_time + PRIMARY_MS - 1
        or confirmed != entry_candle.close_time_ms
        or entry_fill.get("action") != "ENTER_LONG"
        or entry_fill.get("reason") != "NEXT_PRIMARY_OPEN"
        or entry_fill.get("fill_time_ms") != fill_time
        or entry_fill.get("quantity") != RUNNER_QUANTITY
        or portfolio.get("symbol") != symbol
        or portfolio.get("asset_quantity") != RUNNER_QUANTITY
    ):
        raise ShockError("source episode is not a confirmed open Paper entry")
    try:
        quantity = Decimal(portfolio["asset_quantity"])
        cash = Decimal(portfolio["cash"])
        cost_basis = Decimal(portfolio["cost_basis_quote"])
        realized = Decimal(portfolio["realized_pnl_quote"])
    except (InvalidOperation, KeyError, TypeError, ValueError):
        raise ShockError("source portfolio arithmetic is invalid") from None
    if (
        not all(item.is_finite() for item in (quantity, cash, cost_basis, realized))
        or quantity <= 0
        or cash < 0
        or cost_basis <= 0
    ):
        raise ShockError("source portfolio state is invalid")
    return symbol, entry_candle, setup, dict(portfolio)


def _event_for_snapshot(
    *,
    corpus: controls.AdmittedControlCorpus,
    symbol: str,
    decision_time_ms: int,
    registry_sha256: str,
) -> replay.AdmittedEvent:
    return replay.AdmittedEvent(
        event_id=f"CRL-006A-{symbol}",
        designation=corpus.designation,
        quality_manifest_relative_path=(
            corpus.quality_manifest_relative_path
        ),
        quality_manifest_file_sha256=(
            corpus.quality_manifest_file_sha256
        ),
        event_acquisition_manifest_relative_path=(
            corpus.event_acquisition_manifest_relative_path
        ),
        event_acquisition_manifest_sha256=(
            corpus.event_acquisition_manifest_sha256
        ),
        retrieved_at_ms=corpus.retrieved_at_ms,
        event_catalog_sha256=registry_sha256,
        replay_window_start_ms=decision_time_ms,
        replay_window_end_ms=decision_time_ms + PRIMARY_MS,
        replay_start_ms=decision_time_ms,
        replay_end_ms=decision_time_ms + PRIMARY_MS,
        event_anchor_ms=decision_time_ms,
        datasets=corpus.datasets,
    )


def _strategy_before_shock(
    *,
    corpus: controls.AdmittedControlCorpus,
    symbol: str,
    entry_candle: Candle,
    setup: LongSetup,
    registry_sha256: str,
) -> dict[str, object]:
    shock_time = entry_candle.open_time_ms + PRIMARY_MS
    event = _event_for_snapshot(
        corpus=corpus,
        symbol=symbol,
        decision_time_ms=shock_time,
        registry_sha256=registry_sha256,
    )
    try:
        dataset, dataset_sha = replay._dataset_for_symbol(event, symbol)
        snapshot = dataset.snapshot_at(shock_time)
        context = StrategyContext(TREND_PULLBACK_IDENTITY, snapshot)
        decision = evaluate_trend_pullback(
            context,
            in_position=True,
            active_setup=setup,
        )
    except (
        replay.ReplayError,
        BacktestLoadError,
        StrategyContractError,
        TrendStrategyError,
        TypeError,
        ValueError,
    ) as exc:
        raise ShockError("cannot reconstruct point-in-time shock decision") from exc
    if decision.action is StrategyAction.ENTER_LONG:
        raise ShockError("in-position Strategy attempted overlapping entry")
    if (
        not snapshot.primary
        or snapshot.latest_primary.open_time_ms
        != entry_candle.open_time_ms
        or snapshot.latest_primary.close_time_ms
        != entry_candle.close_time_ms
    ):
        raise ShockError(
            "shock decision snapshot is not anchored to entry candle"
        )
    return {
        "decision_time_ms": shock_time,
        "dataset_sha256": dataset_sha,
        "context_sha256": decision.context_sha256,
        "action": decision.action.value,
        "reason": decision.reason.value,
        "future_shock_visible": False,
    }


def _scenario_spec(
    *,
    symbol: str,
    decision_time_ms: int,
    multiplier: int,
) -> BacktestSpec:
    candidate = CandidateFreeze()
    try:
        slippage = Decimal(str(candidate.slippage_bps)) * Decimal(multiplier)
    except Exception:
        raise ShockError("frozen slippage cannot be scaled") from None
    try:
        return BacktestSpec(
            symbol,
            decision_time_ms,
            decision_time_ms + PRIMARY_MS,
            initial_cash=str(candidate.initial_equity_quote),
            fee_bps=str(candidate.fee_bps),
            slippage_bps=_plain(slippage),
        )
    except ValueError:
        raise ShockError("synthetic scenario spec is invalid") from None


def _source_spec(
    *,
    symbol: str,
    decision_time_ms: int,
) -> BacktestSpec:
    candidate = CandidateFreeze()
    try:
        return BacktestSpec(
            symbol,
            decision_time_ms,
            decision_time_ms + PRIMARY_MS,
            initial_cash=str(candidate.initial_equity_quote),
            fee_bps=str(candidate.fee_bps),
            slippage_bps=str(candidate.slippage_bps),
        )
    except ValueError:
        raise ShockError("source valuation spec is invalid") from None


def _synthetic_price(anchor: str, adverse_gap_bps: int) -> str:
    try:
        value = Decimal(anchor)
    except Exception:
        raise ShockError("shock anchor price is invalid") from None
    if (
        not value.is_finite()
        or value <= 0
        or adverse_gap_bps not in (500, 1000, 2000)
    ):
        raise ShockError("shock price inputs are invalid")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        shocked = value * (
            Decimal(1) - Decimal(adverse_gap_bps) / BASIS_POINTS
        )
    return _plain(shocked)


def _synthetic_candle(
    *,
    source: Candle,
    decision_time_ms: int,
    price: str,
) -> Candle:
    try:
        return Candle(
            source=source.source,
            symbol=source.symbol,
            interval="1h",
            open_time_ms=decision_time_ms,
            close_time_ms=decision_time_ms + PRIMARY_MS - 1,
            open=price,
            high=price,
            low=price,
            close=price,
            base_volume=source.base_volume,
            quote_volume=source.quote_volume,
            trade_count=source.trade_count,
            is_closed=True,
        )
    except (TypeError, ValueError):
        raise ShockError("synthetic flat shock candle is invalid") from None


def _exit_reference(
    *,
    strategy_action: str,
    setup: LongSetup,
    shock: Candle,
    quantity: str,
) -> FillReference | None:
    if strategy_action == StrategyAction.EXIT_LONG.value:
        reason = FillReason.SCRIPTED_EXIT
        price = shock.open
    elif strategy_action == StrategyAction.NO_TRADE.value:
        opened = Decimal(shock.open)
        low = Decimal(shock.low)
        high = Decimal(shock.high)
        stop = Decimal(setup.invalidation_price)
        target = Decimal(setup.target_price)
        if opened <= stop:
            price, reason = shock.open, FillReason.STOP
        elif opened >= target:
            price, reason = setup.target_price, FillReason.TARGET
        elif low <= stop and high >= target:
            price, reason = (
                setup.invalidation_price,
                FillReason.AMBIGUOUS_STOP_PRIORITY,
            )
        elif low <= stop:
            price, reason = setup.invalidation_price, FillReason.STOP
        elif high >= target:
            price, reason = setup.target_price, FillReason.TARGET
        else:
            return None
    else:
        raise ShockError("shock Strategy action is invalid")
    try:
        if Decimal(quantity) > Decimal(shock.base_volume):
            raise ShockError(
                "synthetic exit exceeds registered shock-bar base volume"
            )
        return FillReference(
            IntentAction.EXIT_LONG,
            shock.symbol,
            shock.open_time_ms,
            shock.open_time_ms,
            quantity,
            price,
            reason,
        )
    except (
        FillModelError,
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        raise ShockError("synthetic exit reference is invalid") from None


def _liquidation_equity(
    *,
    cash: Decimal,
    quantity: Decimal,
    mark: Decimal,
    spec: BacktestSpec,
) -> Decimal:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        slipped = mark * (
            Decimal(1) - spec.slippage_bps_decimal / BASIS_POINTS
        )
        gross = quantity * slipped
        liquidation = gross * (
            Decimal(1) - spec.fee_bps_decimal / BASIS_POINTS
        )
        return cash + liquidation


def _run_scenario(
    *,
    corpus: controls.AdmittedControlCorpus,
    episode: Mapping[str, object],
    scenario: Mapping[str, object],
    registry_sha256: str,
) -> dict[str, object]:
    symbol, entry_candle, setup, portfolio = _validate_episode(episode)
    episode_id = _episode_identity(episode)
    decision = _strategy_before_shock(
        corpus=corpus,
        symbol=symbol,
        entry_candle=entry_candle,
        setup=setup,
        registry_sha256=registry_sha256,
    )
    gap = scenario.get("adverse_gap_bps")
    multiplier = scenario.get("slippage_multiplier")
    scenario_id = scenario.get("scenario_id")
    if (
        type(gap) is not int
        or type(multiplier) is not int
        or not isinstance(scenario_id, str)
    ):
        raise ShockError("synthetic scenario fields are invalid")
    source_spec = _source_spec(
        symbol=symbol,
        decision_time_ms=decision["decision_time_ms"],
    )
    spec = _scenario_spec(
        symbol=symbol,
        decision_time_ms=decision["decision_time_ms"],
        multiplier=multiplier,
    )
    shock_price = _synthetic_price(entry_candle.close, gap)
    shock = _synthetic_candle(
        source=entry_candle,
        decision_time_ms=decision["decision_time_ms"],
        price=shock_price,
    )

    try:
        cash = Decimal(portfolio["cash"])
        quantity = Decimal(portfolio["asset_quantity"])
        anchor = Decimal(entry_candle.close)
        shocked = Decimal(shock.open)
    except (InvalidOperation, KeyError, TypeError, ValueError):
        raise ShockError("source portfolio cannot seed shock arithmetic") from None

    equity_before = _liquidation_equity(
        cash=cash,
        quantity=quantity,
        mark=anchor,
        spec=source_spec,
    )
    reference = _exit_reference(
        strategy_action=decision["action"],
        setup=setup,
        shock=shock,
        quantity=portfolio["asset_quantity"],
    )
    fill_record = None
    synthetic_cost = Decimal(0)
    if reference is not None:
        try:
            fill = apply_costs(reference, spec)
        except (CostModelError, TypeError, ValueError):
            raise ShockError("synthetic exit cost application failed") from None
        equity_after = cash + fill.cash_delta
        position_after = Decimal(0)
        synthetic_cost = fill.total_cost_quote
        fill_record = _fill_record(fill)
        time_to_zero = 0
        exit_reason = reference.reason.value
    else:
        equity_after = _liquidation_equity(
            cash=cash,
            quantity=quantity,
            mark=shocked,
            spec=spec,
        )
        position_after = quantity
        time_to_zero = None
        exit_reason = None

    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        loss = max(equity_before - equity_after, Decimal(0))
        excursion = (
            loss / equity_before
            if equity_before > 0
            else Decimal(0)
        )
        synthetic_delta = equity_after - equity_before

    result = {
        "schema": "YATL_CRL_006A_IMMEDIATE_SHOCK_SCENARIO",
        "schema_version": SCHEMA_VERSION,
        "implementation_id": IMPLEMENTATION_ID,
        "episode_id": episode_id,
        "symbol": symbol,
        "scenario_id": scenario_id,
        "synthetic_label": "SYNTHETIC",
        "source": {
            "decision_time_ms": episode["decision_time_ms"],
            "fill_time_ms": episode["fill_time_ms"],
            "context_sha256": episode["context_sha256"],
            "entry_candle_sha256": _sha256(
                _canonical_json(episode["entry_candle"])
            ),
            "entry_candle_close": entry_candle.close,
            "source_state_confirmed_at_ms": (
                episode["source_state_confirmed_at_ms"]
            ),
        },
        "scenario": {
            "adverse_gap_bps": gap,
            "slippage_multiplier": multiplier,
            "fee_multiplier": scenario["fee_multiplier"],
            "source_fee_bps": str(source_spec.fee_bps),
            "source_slippage_bps": str(source_spec.slippage_bps),
            "fee_bps": str(spec.fee_bps),
            "slippage_bps": str(spec.slippage_bps),
            "synthetic_open_price": shock.open,
            "shock_bar": shock.as_record(),
            "real_next_candle_used": False,
        },
        "strategy_before_shock_fill": decision,
        "active_setup": {
            "reference_price": setup.reference_price,
            "invalidation_price": setup.invalidation_price,
            "target_price": setup.target_price,
        },
        "immediate": {
            "protective_exit_reason": exit_reason,
            "exit_fill": fill_record,
            "equity_before_shock": _plain(equity_before),
            "equity_after_shock": _plain(equity_after),
            "synthetic_equity_delta": _plain(synthetic_delta),
            "immediate_equity_excursion_fraction": _plain(excursion),
            "position_quantity_after_shock": _plain(position_after),
            "time_to_zero_exposure_ms_if_immediate": time_to_zero,
            "executed_synthetic_cost_quote": _plain(synthetic_cost),
            "kill_switch_evaluated": False,
            "reentry_evaluated": False,
            "recovery_evaluated": False,
        },
        "deterministic_replay_verified": True,
        "point_in_time_verified": True,
        "future_shock_visible_to_strategy": False,
        "historical_pnl": False,
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "paper_only": True,
        "live_master_lock": "OFF",
        "trade_permission": False,
        "order_endpoint": False,
        "quantity_authority": False,
        "risk_authorization_mutation": False,
        "ai_direct_execution": False,
        "p11_locked": True,
    }
    return result


def run_immediate_shock_matrix(
    *,
    runtime_root: Path,
    active_diagnostic_relative_path: str,
    active_diagnostic_file_sha256: str,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, object]:
    registry, registry_sha = load_registry(registry_path)
    active = _load_active_diagnostic(
        runtime_root=runtime_root,
        relative_path=active_diagnostic_relative_path,
        file_sha256=active_diagnostic_file_sha256,
    )
    corpus = _load_corpus_from_active(
        runtime_root=runtime_root,
        active=active,
    )
    scenarios = registry["matrix"]["scenarios"]
    episodes = active["selected_episodes"]

    outputs: list[dict[str, object]] = []
    for episode in episodes:
        for scenario in scenarios:
            first = _run_scenario(
                corpus=corpus,
                episode=episode,
                scenario=scenario,
                registry_sha256=registry_sha,
            )
            second = _run_scenario(
                corpus=corpus,
                episode=episode,
                scenario=scenario,
                registry_sha256=registry_sha,
            )
            if _canonical_json(first) != _canonical_json(second):
                raise ShockError(
                    "CRL-006A scenario replay is not byte-identical"
                )
            outputs.append(first)

    expected_count = len(episodes) * 9
    if len(outputs) != expected_count:
        raise ShockError("CRL-006A scenario matrix is incomplete")

    result: dict[str, object] = {
        "schema": "YATL_CRL_006A_IMMEDIATE_SHOCK_MATRIX",
        "schema_version": SCHEMA_VERSION,
        "implementation_id": IMPLEMENTATION_ID,
        "track_id": registry["track_id"],
        "registry_sha256": registry_sha,
        "active_diagnostic_relative_path": (
            active_diagnostic_relative_path
        ),
        "active_diagnostic_file_sha256": (
            active_diagnostic_file_sha256
        ),
        "active_diagnostic_result_sha256": active["result_sha256"],
        "source_episode_count": len(episodes),
        "scenario_count_per_episode": 9,
        "matrix_result_count": len(outputs),
        "results": outputs,
        "evidence_label": "SYNTHETIC",
        "pool_with_historical_returns": False,
        "pool_with_p10_forward_evidence": False,
        "negative_results_retained": True,
        "deterministic_two_run_equality_verified": True,
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "paper_only": True,
        "live_master_lock": "OFF",
        "trade_permission": False,
        "order_endpoint": False,
        "quantity_authority": False,
        "risk_authorization_mutation": False,
        "ai_direct_execution": False,
        "p11_locked": True,
    }
    result["result_sha256"] = _sha256(_canonical_json(result))
    return result


def _relative_path(digest: str) -> Path:
    return (
        Path("synthetic-shock")
        / "open-position-v0.1.0"
        / f"immediate-shock-{digest[:24]}.json"
    )


def write_result(
    *,
    runtime_root: Path,
    result: Mapping[str, object],
) -> dict[str, object]:
    payload = _canonical_json(result)
    if len(payload) > MAX_RESULT_BYTES:
        raise ShockError("CRL-006A result exceeds bounded size")
    digest = _sha256(payload)
    relative = _relative_path(digest)
    try:
        path = acq._write_immutable(
            runtime_root, relative, payload
        )
    except acq.AcquisitionError as exc:
        raise ShockError(str(exc)) from None
    return {
        "manifest_relative_path": path,
        "manifest_file_sha256": digest,
        "result_sha256": result["result_sha256"],
        "source_episode_count": result["source_episode_count"],
        "matrix_result_count": result["matrix_result_count"],
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


def run_and_write(
    *,
    runtime_root: Path,
    active_diagnostic_relative_path: str,
    active_diagnostic_file_sha256: str,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, object]:
    result = run_immediate_shock_matrix(
        runtime_root=runtime_root,
        active_diagnostic_relative_path=(
            active_diagnostic_relative_path
        ),
        active_diagnostic_file_sha256=(
            active_diagnostic_file_sha256
        ),
        registry_path=registry_path,
    )
    return write_result(runtime_root=runtime_root, result=result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research.crisis_lab.synthetic_shock",
        description=(
            "YATL CRL-006A deterministic immediate open-position shock"
        ),
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--active-diagnostic", required=True)
    parser.add_argument(
        "--active-diagnostic-sha256", required=True
    )
    parser.add_argument(
        "--registry", type=Path, default=DEFAULT_REGISTRY_PATH
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_and_write(
        runtime_root=args.runtime_root,
        active_diagnostic_relative_path=args.active_diagnostic,
        active_diagnostic_file_sha256=(
            args.active_diagnostic_sha256
        ),
        registry_path=args.registry,
    )
    print(_json(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ShockError as exc:
        print(
            _json(
                {
                    "code": "CRL006A_IMMEDIATE_SHOCK_ERROR",
                    "reason": str(exc),
                    "research_only": True,
                    "p10_write_allowed": False,
                    "p11_locked": True,
                }
            )
        )
        raise SystemExit(2)
