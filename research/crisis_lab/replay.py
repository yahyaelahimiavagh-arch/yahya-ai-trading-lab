"""CRL-004 deterministic historical replay over CRL-003 admitted Development data.

Research-only. This module reuses the accepted YATL strategy, P2 Paper fill/cost
engine, and the P10 frozen candidate/risk-veto semantics without reading or
writing the active P10 runtime tree.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from yatl.backtest import (
    AcceptedBacktestDataset,
    BacktestClock,
    BacktestSpec,
    IntentAction,
    PaperFillEngine,
    PaperIntent,
    PortfolioLedger,
    apply_costs,
)
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.strategy import (
    StrategyAction,
    StrategyContext,
    TREND_PULLBACK_IDENTITY,
    evaluate_trend_pullback,
)
from yatl.strategy.adapter import FIXED_RESEARCH_QUANTITY
from yatl.strategy.regime import classify_regime
from yatl.validation.paper_runner import (
    P3_RESEARCH_ADAPTER_GIT_BLOB_SHA1,
    REGIME_WARMUP_BARS,
    RUNNER_QUANTITY,
    _RiskTracker,
    _fill_record,
    _portfolio_record,
    _spec_sha256,
    assess_fixed_quantity_entry,
)
from yatl.validation.registration import CandidateFreeze

from . import acquisition as acq


REPLAY_IMPLEMENTATION_ID = "CRL-004/0.1.0"
REPLAY_SCHEMA_VERSION = "0.1.0"
QUALITY_SCHEMA_VERSION = "0.1.0"
ALLOWED_DESIGNATION = "DEVELOPMENT"
MAX_REPLAY_MANIFEST_BYTES = 8 * 1024 * 1024


class ReplayError(RuntimeError):
    """Historical replay input or deterministic execution failed closed."""


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


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_value(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _plain(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ReplayError("replay arithmetic is not finite")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _safe_root(path: Path) -> Path:
    try:
        return acq.assert_safe_runtime_path(path)
    except acq.AcquisitionError as exc:
        raise ReplayError(str(exc)) from None


def _runtime_path(runtime_root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ReplayError("runtime relative path is missing")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ReplayError("runtime relative path is invalid")
    root = _safe_root(runtime_root)
    try:
        target = acq.assert_safe_runtime_path(root / rel)
    except acq.AcquisitionError as exc:
        raise ReplayError(str(exc)) from None
    try:
        target.relative_to(root)
    except ValueError:
        raise ReplayError("runtime read escaped the research root") from None
    if target.is_symlink():
        raise ReplayError("symlink research artifact is forbidden")
    return target


def _read_bytes(runtime_root: Path, relative: str) -> bytes:
    target = _runtime_path(runtime_root, relative)
    try:
        return target.read_bytes()
    except OSError:
        raise ReplayError("cannot read immutable research artifact") from None


def _load_json(payload: bytes, label: str) -> dict[str, object]:
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ReplayError(f"{label} is not canonical UTF-8 JSON") from None
    if not isinstance(record, dict):
        raise ReplayError(f"{label} must be a JSON object")
    return record


def _require_sha(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ReplayError(f"{label} is not a lowercase SHA-256")
    return value


def _content_address(relative: str, prefix: str, sha256: str) -> None:
    if Path(relative).name != f"{prefix}{sha256[:24]}.json":
        raise ReplayError("content-address filename does not match SHA-256")


def _read_bound_json(
    runtime_root: Path,
    *,
    relative: str,
    sha256: str,
    prefix: str,
    label: str,
) -> dict[str, object]:
    expected = _require_sha(sha256, f"{label} SHA-256")
    _content_address(relative, prefix, expected)
    payload = _read_bytes(runtime_root, relative)
    if _sha256_bytes(payload) != expected:
        raise ReplayError(f"{label} digest mismatch")
    return _load_json(payload, label)


@dataclass(frozen=True, slots=True)
class AdmittedEvent:
    event_id: str
    designation: str
    quality_manifest_relative_path: str
    quality_manifest_file_sha256: str
    event_acquisition_manifest_relative_path: str
    event_acquisition_manifest_sha256: str
    retrieved_at_ms: int
    datasets: dict[tuple[str, str], tuple[Candle, ...]]


def _load_canonical_candles(
    runtime_root: Path,
    *,
    symbol: str,
    interval: str,
    acquisition: Mapping[str, object],
    quality: Mapping[str, object],
) -> tuple[Candle, ...]:
    canonical = acquisition.get("canonical")
    evidence = quality.get("canonical_evidence")
    if not isinstance(canonical, dict) or not isinstance(evidence, dict):
        raise ReplayError("canonical provenance is missing")
    relative = canonical.get("relative_path")
    if not isinstance(relative, str):
        raise ReplayError("canonical relative path is missing")
    expected_sha = _require_sha(canonical.get("sha256"), "canonical SHA-256")
    if evidence.get("canonical_sha256") != expected_sha:
        raise ReplayError("quality/canonical SHA-256 identity mismatch")
    if Path(relative).name != f"dataset-{expected_sha}.csv":
        raise ReplayError("canonical dataset content address is invalid")
    payload = _read_bytes(runtime_root, relative)
    if _sha256_bytes(payload) != expected_sha:
        raise ReplayError("canonical dataset digest mismatch")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise ReplayError("canonical dataset is not UTF-8") from None
    reader = csv.reader(io.StringIO(text, newline=""))
    rows = list(reader)
    if not rows or tuple(rows[0]) != acq.CANONICAL_COLUMNS:
        raise ReplayError("canonical dataset header is invalid")
    candles: list[Candle] = []
    try:
        for row in rows[1:]:
            if len(row) != len(acq.CANONICAL_COLUMNS):
                raise ReplayError("canonical candle column count is invalid")
            candles.append(
                Candle(
                    source=DATA_SOURCE,
                    symbol=symbol,
                    interval=interval,
                    open_time_ms=int(row[0]),
                    close_time_ms=int(row[6]),
                    open=row[1],
                    high=row[2],
                    low=row[3],
                    close=row[4],
                    base_volume=row[5],
                    quote_volume=row[7],
                    trade_count=int(row[8]),
                    is_closed=True,
                )
            )
    except (TypeError, ValueError):
        raise ReplayError("canonical candle violates the accepted P1 contract") from None
    expected_rows = evidence.get("row_count")
    if (
        not candles
        or type(expected_rows) is not int
        or len(candles) != expected_rows
        or len({item.open_time_ms for item in candles}) != len(candles)
        or tuple(item.open_time_ms for item in candles)
        != tuple(sorted(item.open_time_ms for item in candles))
    ):
        raise ReplayError("canonical dataset rows differ from quality evidence")
    duration = INTERVAL_MILLISECONDS[interval]
    expected_grid = tuple(
        range(candles[0].open_time_ms, candles[-1].open_time_ms + duration, duration)
    )
    if tuple(item.open_time_ms for item in candles) != expected_grid:
        raise ReplayError("canonical dataset is not contiguous")
    return tuple(candles)


def load_admitted_event(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
) -> AdmittedEvent:
    root = _safe_root(runtime_root)
    quality_event = _read_bound_json(
        root,
        relative=quality_manifest_relative_path,
        sha256=quality_manifest_file_sha256,
        prefix="event-quality-",
        label="event quality manifest",
    )
    if (
        quality_event.get("schema") != "YATL_CRL_EVENT_QUALITY_MANIFEST"
        or quality_event.get("schema_version") != QUALITY_SCHEMA_VERSION
        or quality_event.get("designation") != ALLOWED_DESIGNATION
        or quality_event.get("overall_status") != "PASS"
        or quality_event.get("replay_admitted") is not True
        or quality_event.get("replay_eligible") is not True
        or quality_event.get("dataset_count") != 6
        or quality_event.get("pass_count") != 6
        or quality_event.get("fail_count") != 0
        or quality_event.get("market_outcomes_exposed") is not False
        or quality_event.get("research_only") is not True
        or quality_event.get("p10_write_allowed") is not False
        or quality_event.get("p11_locked") is not True
        or quality_event.get("trade_permission") is not False
        or quality_event.get("order_endpoint") is not False
        or quality_event.get("ai_direct_execution") is not False
    ):
        raise ReplayError("event is not CRL-003 admitted Development evidence")

    event_id = quality_event.get("event_id")
    if not isinstance(event_id, str):
        raise ReplayError("event identity is missing")

    event_acq_rel = quality_event.get("input_event_acquisition_manifest_relative_path")
    event_acq_sha = quality_event.get("input_event_acquisition_manifest_sha256")
    if not isinstance(event_acq_rel, str):
        raise ReplayError("event acquisition identity is missing")
    event_acq_sha = _require_sha(event_acq_sha, "event acquisition SHA-256")
    event_acq = _read_bound_json(
        root,
        relative=event_acq_rel,
        sha256=event_acq_sha,
        prefix="event-acquisition-",
        label="event acquisition manifest",
    )
    if (
        event_acq.get("schema") != "YATL_CRL_EVENT_ACQUISITION_PROVENANCE"
        or event_acq.get("schema_version") != "0.1.0"
        or event_acq.get("event_id") != event_id
        or event_acq.get("designation") != ALLOWED_DESIGNATION
        or event_acq.get("overall_status") != "COMPLETE"
        or event_acq.get("replay_eligible") is not True
        or event_acq.get("research_only") is not True
        or event_acq.get("p10_write_allowed") is not False
        or event_acq.get("p11_locked") is not True
    ):
        raise ReplayError("event acquisition provenance is inconsistent")
    retrieved_at = event_acq.get("retrieved_at_utc")
    if not isinstance(retrieved_at, str):
        raise ReplayError("event acquisition retrieval time is missing")
    try:
        retrieved_at_ms = acq._iso_to_ms(retrieved_at)
    except acq.AcquisitionError as exc:
        raise ReplayError(str(exc)) from None

    dataset_refs = quality_event.get("datasets")
    if not isinstance(dataset_refs, list) or len(dataset_refs) != 6:
        raise ReplayError("event quality dataset scope is incomplete")
    expected_pairs = {
        (symbol, interval)
        for symbol in acq.ALLOWED_SYMBOLS
        for interval in acq.ALLOWED_INTERVALS
    }
    loaded: dict[tuple[str, str], tuple[Candle, ...]] = {}
    for item in dataset_refs:
        if not isinstance(item, dict):
            raise ReplayError("dataset quality reference is invalid")
        symbol = item.get("symbol")
        interval = item.get("interval")
        if (symbol, interval) not in expected_pairs or (symbol, interval) in loaded:
            raise ReplayError("dataset quality identity set is invalid")
        if (
            item.get("quality_status") != "PASS"
            or item.get("replay_admitted") is not True
            or item.get("failure_codes") != []
        ):
            raise ReplayError("dataset is not quality-admitted")
        qrel = item.get("quality_manifest_relative_path")
        qsha = item.get("quality_manifest_file_sha256")
        if not isinstance(qrel, str):
            raise ReplayError("dataset quality path is missing")
        qsha = _require_sha(qsha, "dataset quality SHA-256")
        dataset_quality = _read_bound_json(
            root,
            relative=qrel,
            sha256=qsha,
            prefix="quality-",
            label="dataset quality manifest",
        )
        if (
            dataset_quality.get("schema") != "YATL_CRL_DATASET_QUALITY_MANIFEST"
            or dataset_quality.get("schema_version") != QUALITY_SCHEMA_VERSION
            or dataset_quality.get("event_id") != event_id
            or dataset_quality.get("designation") != ALLOWED_DESIGNATION
            or dataset_quality.get("symbol") != symbol
            or dataset_quality.get("interval") != interval
            or dataset_quality.get("quality_status") != "PASS"
            or dataset_quality.get("replay_admitted") is not True
            or dataset_quality.get("failure_codes") != []
            or dataset_quality.get("market_outcomes_exposed") is not False
            or dataset_quality.get("research_only") is not True
            or dataset_quality.get("p10_write_allowed") is not False
            or dataset_quality.get("p11_locked") is not True
        ):
            raise ReplayError("dataset quality provenance is inconsistent")

        arel = dataset_quality.get("input_acquisition_manifest_relative_path")
        asha = dataset_quality.get("input_acquisition_manifest_sha256")
        if not isinstance(arel, str):
            raise ReplayError("dataset acquisition path is missing")
        asha = _require_sha(asha, "dataset acquisition SHA-256")
        acquisition = _read_bound_json(
            root,
            relative=arel,
            sha256=asha,
            prefix="acquisition-",
            label="dataset acquisition manifest",
        )
        if (
            acquisition.get("schema") != "YATL_CRL_DATASET_ACQUISITION_PROVENANCE"
            or acquisition.get("schema_version") != "0.1.0"
            or acquisition.get("event_id") != event_id
            or acquisition.get("designation") != ALLOWED_DESIGNATION
            or acquisition.get("symbol") != symbol
            or acquisition.get("interval") != interval
            or acquisition.get("replay_eligible") is not True
            or acquisition.get("research_only") is not True
            or acquisition.get("p10_write_allowed") is not False
            or acquisition.get("p11_locked") is not True
        ):
            raise ReplayError("dataset acquisition provenance is inconsistent")

        loaded[(str(symbol), str(interval))] = _load_canonical_candles(
            root,
            symbol=str(symbol),
            interval=str(interval),
            acquisition=acquisition,
            quality=dataset_quality,
        )
    if set(loaded) != expected_pairs:
        raise ReplayError("admitted event dataset scope is incomplete")
    return AdmittedEvent(
        event_id=event_id,
        designation=ALLOWED_DESIGNATION,
        quality_manifest_relative_path=quality_manifest_relative_path,
        quality_manifest_file_sha256=quality_manifest_file_sha256,
        event_acquisition_manifest_relative_path=event_acq_rel,
        event_acquisition_manifest_sha256=event_acq_sha,
        retrieved_at_ms=retrieved_at_ms,
        datasets=loaded,
    )


def _dataset_digest(values: Mapping[str, tuple[Candle, ...]]) -> str:
    return _sha256_value([
        item.as_record()
        for interval in ("15m", "1h", "4h")
        for item in values[interval]
    ])


def _dataset_for_symbol(
    event: AdmittedEvent, symbol: str
) -> tuple[AcceptedBacktestDataset, str]:
    candidate = CandidateFreeze()
    if (
        candidate.strategy_id != "TREND_PULLBACK"
        or candidate.strategy_version != "1.0.0"
        or candidate.symbols != acq.ALLOWED_SYMBOLS
        or candidate.primary_interval != "1h"
        or candidate.context_interval != "15m"
        or candidate.regime_interval != "4h"
        or RUNNER_QUANTITY != FIXED_RESEARCH_QUANTITY
    ):
        raise ReplayError("frozen candidate differs from CRL-004 replay contract")
    values = {
        interval: event.datasets[(symbol, interval)]
        for interval in acq.ALLOWED_INTERVALS
    }
    first_decision = (
        values["4h"][0].open_time_ms
        + REGIME_WARMUP_BARS * INTERVAL_MILLISECONDS["4h"]
    )
    common_end = min(
        candles[-1].open_time_ms + INTERVAL_MILLISECONDS[interval]
        for interval, candles in values.items()
    )
    common_end = (
        common_end // INTERVAL_MILLISECONDS["1h"]
    ) * INTERVAL_MILLISECONDS["1h"]
    if common_end <= first_decision:
        raise ReplayError("admitted event lacks frozen strategy warmup")
    spec = BacktestSpec(
        symbol,
        first_decision,
        common_end,
        initial_cash=candidate.initial_equity_quote,
        fee_bps=candidate.fee_bps,
        slippage_bps=candidate.slippage_bps,
    )
    dataset = AcceptedBacktestDataset(
        spec=spec,
        manifest_generated_at_ms=event.retrieved_at_ms,
        primary=values["1h"],
        context=values["15m"],
        regime=values["4h"],
    )
    return dataset, _dataset_digest(values)


def _drawdown(equities: list[Decimal]) -> tuple[str, str]:
    if not equities or any(
        not value.is_finite() or value <= 0 for value in equities
    ):
        raise ReplayError("sampled equity curve is invalid")
    peak = equities[0]
    maximum_quote = Decimal(0)
    maximum_fraction = Decimal(0)
    for equity in equities:
        peak = max(peak, equity)
        loss = peak - equity
        maximum_quote = max(maximum_quote, loss)
        maximum_fraction = max(maximum_fraction, loss / peak)
    return _plain(maximum_quote), _plain(maximum_fraction)


def _economics(
    *,
    initial_cash: str,
    final_portfolio: Mapping[str, object],
    trace: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    initial = Decimal(initial_cash)
    final_equity = Decimal(str(final_portfolio["equity_quote"]))
    equities = [initial]
    for row in trace:
        risk = row.get("risk_state")
        if not isinstance(risk, dict):
            raise ReplayError("trace risk state is missing")
        equities.append(Decimal(str(risk["equity_quote"])))
    equities.append(final_equity)
    drawdown_quote, drawdown_fraction = _drawdown(equities)
    fee = Decimal(str(final_portfolio["total_fee_quote"]))
    slip = Decimal(str(final_portfolio["total_slippage_quote"]))
    net = final_equity - initial
    asset = Decimal(str(final_portfolio["asset_quantity"]))
    return {
        "initial_equity_quote": _plain(initial),
        "final_equity_quote": _plain(final_equity),
        "net_pnl_after_costs_quote": _plain(net),
        "net_return_after_costs": _plain(net / initial),
        "realized_net_pnl_quote": str(final_portfolio["realized_pnl_quote"]),
        "unrealized_liquidation_net_pnl_quote": str(
            final_portfolio["unrealized_pnl_quote"]
        ),
        "executed_fee_quote": _plain(fee),
        "executed_slippage_quote": _plain(slip),
        "executed_total_cost_quote": _plain(fee + slip),
        "completed_trades": int(final_portfolio["closed_trades"]),
        "open_positions": int(asset > 0),
        "sampled_liquidation_drawdown": {
            "maximum_drawdown_quote": drawdown_quote,
            "maximum_drawdown_fraction": drawdown_fraction,
        },
    }


def _run_symbol(event: AdmittedEvent, symbol: str) -> dict[str, object]:
    dataset, input_sha = _dataset_for_symbol(event, symbol)
    events = tuple(BacktestClock(dataset).events())
    if not events:
        raise ReplayError("historical replay has no legal decision event")
    by_open = {item.open_time_ms: item for item in dataset.primary}
    if len(by_open) != len(dataset.primary):
        raise ReplayError("historical primary candles are duplicated")

    fill_engine = PaperFillEngine(symbol)
    ledger = PortfolioLedger(dataset.spec)
    risk_tracker = _RiskTracker(
        symbol, CandidateFreeze().initial_equity_quote
    )
    active_setup = None
    trace: list[dict[str, object]] = []
    fills: list[dict[str, object]] = []
    counts = {
        "entry": 0,
        "allowed": 0,
        "blocked": 0,
        "exit": 0,
        "no_trade": 0,
    }
    regime_counts: dict[str, int] = {}

    for decision_event in events:
        fill_candle = by_open.get(decision_event.eligible_fill_open_time_ms)
        if fill_candle is None or not fill_candle.is_closed:
            raise ReplayError(
                "historical next-open candle is missing or not closed"
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
            raise ReplayError("historical decision contains future data")

        pre = ledger.snapshot(decision_event.snapshot.latest_primary.close)
        risk_state = risk_tracker.observe(
            decision_event.decision_time_ms,
            pre,
            decision_event.snapshot.latest_primary.close,
        )
        context = StrategyContext(
            TREND_PULLBACK_IDENTITY, decision_event.snapshot
        )
        regime = classify_regime(context)
        regime_counts[regime.regime.value] = (
            regime_counts.get(regime.regime.value, 0) + 1
        )
        decision = evaluate_trend_pullback(
            context,
            in_position=fill_engine.has_position,
            active_setup=active_setup,
        )

        veto = None
        if decision.action is StrategyAction.ENTER_LONG:
            counts["entry"] += 1
            veto = assess_fixed_quantity_entry(decision, risk_state)
            if veto.allowed:
                counts["allowed"] += 1
                intent = PaperIntent(
                    IntentAction.ENTER_LONG,
                    decision_event.decision_time_ms,
                    RUNNER_QUANTITY,
                    decision.setup.invalidation_price,
                    decision.setup.target_price,
                )
            else:
                counts["blocked"] += 1
                intent = PaperIntent(
                    IntentAction.HOLD, decision_event.decision_time_ms
                )
        elif decision.action is StrategyAction.EXIT_LONG:
            counts["exit"] += 1
            intent = PaperIntent(
                IntentAction.EXIT_LONG, decision_event.decision_time_ms
            )
        else:
            counts["no_trade"] += 1
            intent = PaperIntent(
                IntentAction.HOLD, decision_event.decision_time_ms
            )

        references = fill_engine.process(
            decision_event, intent, fill_candle
        )
        costed = tuple(
            apply_costs(item, dataset.spec) for item in references
        )
        if costed:
            ledger.apply_many(costed)
            fills.extend(_fill_record(item) for item in costed)

        if fill_engine.has_position:
            if intent.action is IntentAction.ENTER_LONG:
                active_setup = decision.setup
            elif active_setup is None:
                raise ReplayError(
                    "historical Paper position lost its frozen setup"
                )
        else:
            active_setup = None

        post = ledger.snapshot(fill_candle.open)
        trace.append({
            "sequence": decision_event.sequence,
            "decision_time_ms": decision_event.decision_time_ms,
            "context_sha256": decision.context_sha256,
            "regime": regime.regime.value,
            "regime_reason": regime.reason.value,
            "strategy_action": decision.action.value,
            "strategy_reason": decision.reason.value,
            "effective_intent": intent.action.value,
            "entry_veto": (
                None if veto is None else veto.as_record()
            ),
            "risk_state": risk_state.as_record(),
            "fill_count": len(costed),
            "post_position_quantity": _plain(post.asset_quantity),
            "post_equity_quote": _plain(post.equity_quote),
        })

    final_mark = dataset.primary[-1].close
    final_portfolio = _portfolio_record(ledger.snapshot(final_mark))
    economics = _economics(
        initial_cash=CandidateFreeze().initial_equity_quote,
        final_portfolio=final_portfolio,
        trace=trace,
    )
    first_kill = next(
        (
            row["decision_time_ms"]
            for row in trace
            if row["risk_state"]["kill_switch_active"] is True
        ),
        None,
    )
    result = {
        "symbol": symbol,
        "spec_sha256": _spec_sha256(dataset.spec),
        "input_dataset_sha256": input_sha,
        "first_decision_time_ms": dataset.spec.start_time_ms,
        "end_time_ms": dataset.spec.end_time_ms,
        "event_count": len(events),
        "entry_signals": counts["entry"],
        "entries_allowed": counts["allowed"],
        "entries_blocked": counts["blocked"],
        "exit_signals": counts["exit"],
        "no_trade_signals": counts["no_trade"],
        "regime_counts": dict(sorted(regime_counts.items())),
        "kill_switch_latched": risk_tracker.kill_switch_active,
        "first_kill_switch_time_ms": first_kill,
        "trace": trace,
        "fills": fills,
        "final_portfolio": final_portfolio,
        "economics": economics,
        "point_in_time_verified": True,
        "replay_from_admitted_start": True,
    }
    result["result_sha256"] = _sha256_value(result)
    return result


def _run_event(event: AdmittedEvent) -> dict[str, object]:
    candidate = CandidateFreeze()
    symbols = [
        _run_symbol(event, symbol)
        for symbol in candidate.symbols
    ]
    return {
        "schema": "YATL_CRL_HISTORICAL_REPLAY",
        "schema_version": REPLAY_SCHEMA_VERSION,
        "implementation_id": REPLAY_IMPLEMENTATION_ID,
        "event_id": event.event_id,
        "designation": event.designation,
        "input_quality_manifest_relative_path": (
            event.quality_manifest_relative_path
        ),
        "input_quality_manifest_file_sha256": (
            event.quality_manifest_file_sha256
        ),
        "input_event_acquisition_manifest_relative_path": (
            event.event_acquisition_manifest_relative_path
        ),
        "input_event_acquisition_manifest_sha256": (
            event.event_acquisition_manifest_sha256
        ),
        "candidate": {
            "candidate_id": candidate.candidate_id,
            "candidate_sha256": candidate.candidate_sha256,
            "strategy_id": candidate.strategy_id,
            "strategy_version": candidate.strategy_version,
            "configuration_sha256": candidate.configuration_sha256,
            "fixed_research_quantity": RUNNER_QUANTITY,
            "p3_adapter_git_blob_sha1": (
                P3_RESEARCH_ADAPTER_GIT_BLOB_SHA1
            ),
            "initial_equity_quote_per_symbol": (
                candidate.initial_equity_quote
            ),
            "fee_bps": candidate.fee_bps,
            "slippage_bps": candidate.slippage_bps,
            "execution_price_policy": (
                candidate.execution_price_policy
            ),
        },
        "symbols": symbols,
        "deterministic_replay_verified": True,
        "point_in_time_verified": True,
        "future_data_visible_to_strategy": False,
        "post_event_label_visible_to_strategy": False,
        "market_outcomes_exposed": True,
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "paper_only": True,
        "live_master_lock": "OFF",
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
        "p11_locked": True,
    }


def _replay_relative_path(event_id: str, digest: str) -> Path:
    return (
        Path("replay")
        / f"event-catalog-v{acq.CATALOG_VERSION}"
        / event_id
        / f"event-replay-{digest[:24]}.json"
    )


def _write_immutable(
    runtime_root: Path, relative: Path, payload: bytes
) -> str:
    if len(payload) > MAX_REPLAY_MANIFEST_BYTES:
        raise ReplayError("replay manifest exceeds bounded size")
    try:
        return acq._write_immutable(runtime_root, relative, payload)
    except acq.AcquisitionError as exc:
        raise ReplayError(str(exc)) from None


def replay_event(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
) -> dict[str, object]:
    event = load_admitted_event(
        runtime_root=runtime_root,
        quality_manifest_relative_path=(
            quality_manifest_relative_path
        ),
        quality_manifest_file_sha256=(
            quality_manifest_file_sha256
        ),
    )
    first = _run_event(event)
    second = _run_event(event)
    if _json(first) != _json(second):
        raise ReplayError("historical replay is not byte-deterministic")
    payload = _canonical_json(first)
    file_sha = _sha256_bytes(payload)
    relative = _replay_relative_path(event.event_id, file_sha)
    relative_text = _write_immutable(
        runtime_root, relative, payload
    )
    result = dict(first)
    result["replay_manifest_file_sha256"] = file_sha
    result["replay_manifest_relative_path"] = relative_text
    return result


def safe_summary(
    result: Mapping[str, object]
) -> dict[str, object]:
    symbols = result.get("symbols")
    candidate = result.get("candidate")
    if not isinstance(symbols, list) or not isinstance(candidate, dict):
        raise ReplayError("replay result summary is incomplete")
    return {
        "event_id": result["event_id"],
        "designation": result["designation"],
        "candidate_id": candidate["candidate_id"],
        "candidate_sha256": candidate["candidate_sha256"],
        "symbols": [
            {
                "symbol": item["symbol"],
                "event_count": item["event_count"],
                "entry_signals": item["entry_signals"],
                "entries_allowed": item["entries_allowed"],
                "entries_blocked": item["entries_blocked"],
                "exit_signals": item["exit_signals"],
                "no_trade_signals": item["no_trade_signals"],
                "regime_counts": item["regime_counts"],
                "kill_switch_latched": item[
                    "kill_switch_latched"
                ],
                "fills": len(item["fills"]),
                "economics": item["economics"],
                "result_sha256": item["result_sha256"],
            }
            for item in symbols
        ],
        "deterministic_replay_verified": result[
            "deterministic_replay_verified"
        ],
        "point_in_time_verified": result[
            "point_in_time_verified"
        ],
        "future_data_visible_to_strategy": False,
        "post_event_label_visible_to_strategy": False,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "p11_locked": True,
        "replay_manifest_relative_path": result[
            "replay_manifest_relative_path"
        ],
        "replay_manifest_file_sha256": result[
            "replay_manifest_file_sha256"
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research.crisis_lab.replay",
        description=(
            "YATL CRL-004 deterministic Development-event replay"
        ),
    )
    parser.add_argument(
        "--runtime-root", type=Path, required=True
    )
    parser.add_argument(
        "--quality-manifest", required=True
    )
    parser.add_argument(
        "--quality-manifest-sha256", required=True
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = replay_event(
        runtime_root=args.runtime_root,
        quality_manifest_relative_path=args.quality_manifest,
        quality_manifest_file_sha256=(
            args.quality_manifest_sha256
        ),
    )
    print(_json(safe_summary(result)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReplayError as exc:
        print(_json({
            "code": "CRL004_REPLAY_ERROR",
            "reason": str(exc),
            "research_only": True,
            "p10_read": False,
            "p10_write_allowed": False,
            "p11_locked": True,
        }))
        raise SystemExit(4)
