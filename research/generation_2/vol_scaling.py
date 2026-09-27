"""GEN2-002 lagged volatility-scaling Development runner.

Research only. Implements the preregistered YATL internal adaptation of
RIE-CAND-0025. It reads only the known CRL Development corpus and frozen
HSSE-004A reference strategies. It never reads 2023-2024 known diagnostics,
Fresh OOS, recent reserve, P10 state, credentials, accounts, or order endpoints.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Mapping, Sequence

from research.crisis_lab import controls
from research.historical_strategy_search import survivor_ranking as hsse3
from research.historical_strategy_search import trend_ma as hsse2
from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.data import INTERVAL_MILLISECONDS

IMPLEMENTATION_ID = "GEN2-002-VOL-SCALING/0.1.0"
SCHEMA_VERSION = "0.1.0"
HOUR_MS = INTERVAL_MILLISECONDS["1h"]
DAY_MS = 24 * HOUR_MS
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROTOCOL_PATH = REPO_ROOT / (
    "docs/research/generation-2/"
    "GEN2-002-VOL-SCALING-PROTOCOL-v0.1.0.json"
)
MAX_PROTOCOL_BYTES = 2 * 1024 * 1024
MAX_BOUND_BYTES = 4 * 1024 * 1024


class Gen2VolError(RuntimeError):
    """GEN2-002 violated a frozen research or accounting boundary."""


@dataclass(slots=True)
class _Account:
    cash: Decimal
    quantity: Decimal
    cycle_cashflow: Decimal | None
    realized: list[Decimal]
    total_fee: Decimal
    total_slippage: Decimal
    total_turnover: Decimal


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


def _git_blob_sha(payload: bytes) -> str:
    header = ("blob " + str(len(payload))).encode("ascii") + bytes([0])
    return hashlib.sha1(header + payload).hexdigest()


def _plain(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not value.is_finite():
        raise Gen2VolError("non-finite Decimal")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _time_ms(value: object, label: str) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise Gen2VolError(label + " is not UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise Gen2VolError(label + " is invalid") from None
    return int(parsed.timestamp() * 1000)


def _read_repo_bound(
    binding: Mapping[str, object], label: str
) -> tuple[dict[str, object], bytes]:
    relative = binding.get("relative_path")
    expected = binding.get("git_blob_sha")
    if not isinstance(relative, str) or not isinstance(expected, str) or len(expected) != 40:
        raise Gen2VolError(label + " binding is invalid")
    target = (REPO_ROOT / relative).resolve()
    if not target.is_relative_to(REPO_ROOT.resolve()) or target.is_symlink():
        raise Gen2VolError(label + " path is unsafe")
    try:
        payload = target.read_bytes()
    except OSError:
        raise Gen2VolError("cannot read " + label) from None
    if not payload or len(payload) > MAX_BOUND_BYTES:
        raise Gen2VolError(label + " size is invalid")
    if _git_blob_sha(payload) != expected:
        raise Gen2VolError(label + " Git blob binding mismatch")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise Gen2VolError(label + " is not UTF-8 JSON") from None
    if not isinstance(record, dict):
        raise Gen2VolError(label + " must be an object")
    return record, payload


def validate_protocol(
    path: Path = DEFAULT_PROTOCOL_PATH,
) -> tuple[dict[str, object], str, dict[str, object], dict[str, object]]:
    target = path.resolve()
    if not target.is_relative_to(REPO_ROOT.resolve()) or target.is_symlink():
        raise Gen2VolError("protocol path is unsafe")
    try:
        payload = target.read_bytes()
    except OSError:
        raise Gen2VolError("cannot read GEN2-002 protocol") from None
    if not payload or len(payload) > MAX_PROTOCOL_BYTES:
        raise Gen2VolError("GEN2-002 protocol size is invalid")
    try:
        p = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise Gen2VolError("GEN2-002 protocol is not UTF-8 JSON") from None

    if (
        not isinstance(p, dict)
        or p.get("schema") != "YATL_GEN2_VOLATILITY_SCALING_PROTOCOL"
        or p.get("schema_version") != SCHEMA_VERSION
        or p.get("protocol_id") != "GEN2-002-VOL-SCALING-001"
        or p.get("status") != "REGISTERED_BEFORE_GEN2_VOL_SCALING_OUTCOMES"
        or p.get("source_candidate_id") != "RIE-CAND-0025"
        or p.get("tested_object_id") != "GEN2-ADAPT-0002-VOL-SCALING"
        or p.get("tested_object_type") != "YATL_INTERNAL_ADAPTATION"
        or p.get("research_only") is not True
        or p.get("p10_read") is not False
        or p.get("p10_write_allowed") is not False
        or p.get("p11_locked") is not True
        or p.get("live_master_lock") != "OFF"
        or p.get("no_rerank_after_outcomes") is not True
        or p.get("no_retune_after_outcomes") is not True
    ):
        raise Gen2VolError("GEN2-002 identity/safety is invalid")

    scope = p.get("development_scope")
    est = p.get("volatility_estimator")
    scale = p.get("scaling_rule")
    execution = p.get("execution")
    matrix = p.get("trial_matrix")
    opp = p.get("opportunity_preservation")
    gate = p.get("proposal_gate")
    refs = p.get("reference_strategies")
    bindings = p.get("bindings")
    amendment = p.get("pre_performance_binding_amendment")
    if not all(
        isinstance(x, dict)
        for x in (scope, est, scale, execution, matrix, opp, gate, refs, bindings, amendment)
    ):
        raise Gen2VolError("GEN2-002 scope is incomplete")

    expected_folds = [
        ("GEN2-D001", "2020-08-01T00:00:00Z", "2021-01-01T00:00:00Z"),
        ("GEN2-D002", "2021-01-01T00:00:00Z", "2021-07-01T00:00:00Z"),
        ("GEN2-D003", "2021-07-01T00:00:00Z", "2022-01-01T00:00:00Z"),
        ("GEN2-D004", "2022-01-01T00:00:00Z", "2022-07-01T00:00:00Z"),
        ("GEN2-D005", "2022-07-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    ]
    folds = scope.get("development_folds")
    if (
        scope.get("corpus_id") != "CRL-CONTROL-DEV-POOL-001"
        or scope.get("estimator_warmup_start_utc") != "2020-01-01T00:00:00Z"
        or scope.get("scored_analysis_start_utc") != "2020-08-01T00:00:00Z"
        or scope.get("analysis_end_exclusive_utc") != "2023-01-01T00:00:00Z"
        or scope.get("selection_only") is not True
        or scope.get("hsse_004b_2023_2024_read_allowed") is not False
        or scope.get("hsse_005_outcomes_used_for_selection") is not False
        or scope.get("fresh_oos_read_allowed") is not False
        or scope.get("recent_reserve_read_allowed") is not False
        or not isinstance(folds, list)
        or [(x.get("fold_id"), x.get("evaluation_start_utc"), x.get("evaluation_end_exclusive_utc")) for x in folds]
        != expected_folds
    ):
        raise Gen2VolError("GEN2-002 Development boundary is invalid")

    if (
        est.get("window_completed_utc_days") != 183
        or est.get("annualization_days") != 365
        or est.get("update_frequency") != "MONTHLY_AT_UTC_BOUNDARY_WITH_NEXT_OPEN_EFFECT"
        or est.get("fee_slippage_excluded_from_risk_estimator") is not True
        or scale.get("target_annualized_volatility") != "0.12"
        or scale.get("scale_cap") != "1.0"
        or scale.get("positive_scale_floor") is not None
        or scale.get("leverage_forbidden") is not True
        or scale.get("short_forbidden") is not True
        or scale.get("directional_signal_creation_forbidden") is not True
        or scale.get("alternate_targets_forbidden") is not True
        or scale.get("alternate_windows_forbidden") is not True
        or scale.get("ewma_variants_forbidden") is not True
    ):
        raise Gen2VolError("GEN2-002 estimator/scaler is invalid")

    if (
        execution.get("timeframe") != "1h"
        or execution.get("mode") != "LONG_ONLY_SPOT_RESEARCH"
        or execution.get("base_quantity") != "0.001"
        or execution.get("initial_equity_quote") != "10000"
        or execution.get("base_fee_bps") != 10
        or execution.get("base_adverse_slippage_bps") != 5
        or execution.get("stress_fee_bps") != 20
        or execution.get("stress_adverse_slippage_bps") != 10
    ):
        raise Gen2VolError("GEN2-002 execution policy is invalid")

    if (
        matrix.get("conditions") != ["CONTROL_UNSCALED", "VOL_SCALED_12PCT_NO_LEVERAGE"]
        or matrix.get("reference_strategy_count") != 6
        or matrix.get("conditions_per_strategy") != 2
        or matrix.get("total_conditions") != 12
        or matrix.get("target_count") != 1
        or matrix.get("window_count") != 1
        or matrix.get("cap_count") != 1
        or matrix.get("hidden_trials_forbidden") is not True
        or matrix.get("failed_trials_retained") is not True
        or matrix.get("post_outcome_trial_budget_expansion_forbidden") is not True
    ):
        raise Gen2VolError("GEN2-002 trial matrix is invalid")

    if (
        opp.get("directional_entry_signal_count_must_equal_control") is not True
        or opp.get("completed_directional_trade_count_must_equal_control") is not True
        or opp.get("active_exposure_hours_fraction_vs_control_minimum") != "1.0"
        or opp.get("notional_exposure_ratio_vs_control_minimum") != "0.25"
        or gate.get("minimum_reference_strategies_with_scale_below_one") != 4
        or gate.get("minimum_scaled_entry_or_rebalance_events_total") != 6
        or gate.get("opportunity_preservation_must_pass") is not True
        or gate.get("aggregate_scaled_base_net_must_be_positive") is not True
        or gate.get("aggregate_scaled_stress_net_must_be_positive") is not True
        or gate.get("aggregate_base_net_must_exceed_control") is not True
        or gate.get("aggregate_stress_net_must_exceed_control") is not True
        or gate.get("median_reference_strategy_base_net_delta_must_be_positive") is not True
        or gate.get("median_reference_strategy_stress_net_delta_must_be_positive") is not True
        or gate.get("median_reference_strategy_drawdown_delta_must_be_negative") is not True
        or gate.get("at_least_reference_strategies_with_nonworse_drawdown") != 4
        or gate.get("zero_proposals_is_valid") is not True
    ):
        raise Gen2VolError("GEN2-002 gate is invalid")

    if (
        amendment.get("status") != "BOUND_BEFORE_ANY_GEN2_002_PERFORMANCE_OUTCOME"
        or amendment.get("parameter_changes") is not False
        or amendment.get("target_window_cap_changes") is not False
        or amendment.get("trial_budget_changes") is not False
        or amendment.get("outcome_accessed") is not False
    ):
        raise Gen2VolError("GEN2-002 pre-performance binding amendment is invalid")

    extraction, _ = _read_repo_bound(bindings["method_extraction"], "RIE-CAND-0025 extraction")
    freeze, _ = _read_repo_bound(bindings["survivor_freeze"], "HSSE-004A freeze")
    master, _ = _read_repo_bound(bindings["gen2_master_protocol"], "GEN2 master protocol")
    hsse, _ = _read_repo_bound(bindings["hsse_search_protocol"], "HSSE-001 protocol")
    if (
        extraction.get("candidate_id") != "RIE-CAND-0025"
        or extraction.get("status") != "METHOD_EXACT_ADAPTATION_PROTOCOL_REGISTERED"
        or extraction.get("performance_run_allowed") is not False
        or extraction.get("reproducibility_assessment", {}).get("full_source_replication_claim_allowed") is not False
    ):
        raise Gen2VolError("RIE-CAND-0025 extraction binding is invalid")
    survivors = freeze.get("survivors")
    if (
        freeze.get("freeze_id") != "HSSE-004A-SURVIVOR-FREEZE-001"
        or not isinstance(survivors, list)
        or len(survivors) != 6
        or [x.get("frozen_id") for x in survivors] != refs.get("frozen_ids")
    ):
        raise Gen2VolError("HSSE-004A survivor binding is invalid")
    if (
        master.get("protocol_id") != "GEN2-MASTER-001"
        or master.get("p10_independent") is not True
        or master.get("p11_locked") is not True
        or master.get("evidence_map", {}).get("fresh_oos", {}).get("status")
        != "SEALED_UNTIL_GEN2_SURVIVOR_FREEZE"
    ):
        raise Gen2VolError("GEN2 master binding is invalid")
    if hsse.get("protocol_id") != "HSSE-001-SEARCH-PROTOCOL":
        raise Gen2VolError("HSSE-001 binding is invalid")
    q = bindings.get("development_quality_manifest")
    if (
        not isinstance(q, dict)
        or q.get("relative_path")
        != "quality/event-catalog-v0.1.0/CRL-CONTROL-DEV-POOL-001/event-quality-74ea7a7084bb138122ee5d82.json"
        or q.get("file_sha256")
        != "74ea7a7084bb138122ee5d823c790853ad55cb57e1378a876bec6d3f1537167e"
    ):
        raise Gen2VolError("Development quality-manifest binding is invalid")
    return p, _sha256(payload), freeze, hsse


def _series(corpus: controls.AdmittedControlCorpus, symbol: str):
    candles = corpus.datasets[(symbol, "1h")]
    times = tuple(x.open_time_ms for x in candles)
    if (
        not candles
        or times != tuple(sorted(times))
        or len(times) != len(set(times))
        or any(not x.is_closed for x in candles)
    ):
        raise Gen2VolError("invalid Development 1h series for " + symbol)
    signal = hsse2.SearchSeries(
        symbol,
        times,
        tuple(float(x.open) for x in candles),
        tuple(float(x.close) for x in candles),
    )
    exact = hsse3.ExactSeries(
        symbol,
        times,
        tuple(x.open for x in candles),
        tuple(x.close for x in candles),
    )
    return signal, exact


def _new_account(initial: Decimal) -> _Account:
    return _Account(
        cash=initial,
        quantity=Decimal(0),
        cycle_cashflow=None,
        realized=[],
        total_fee=Decimal(0),
        total_slippage=Decimal(0),
        total_turnover=Decimal(0),
    )


def _buy(
    account: _Account,
    *,
    reference: Decimal,
    quantity: Decimal,
    fee_bps: Decimal,
    slippage_bps: Decimal,
    start_cycle: bool,
) -> None:
    if quantity < 0:
        raise Gen2VolError("negative buy quantity")
    if start_cycle:
        if account.cycle_cashflow is not None or account.quantity != 0:
            raise Gen2VolError("overlapping directional entry")
        account.cycle_cashflow = Decimal(0)
    elif account.cycle_cashflow is None:
        raise Gen2VolError("rebalance buy outside directional cycle")
    if quantity == 0:
        return
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        fee_rate = fee_bps / Decimal(10000)
        slip_rate = slippage_bps / Decimal(10000)
        execution = reference * (Decimal(1) + slip_rate)
        gross = quantity * execution
        fee = gross * fee_rate
        debit = gross + fee
        slip = quantity * (execution - reference)
        new_cash = account.cash - debit
    if new_cash < 0:
        raise Gen2VolError("insufficient research cash")
    account.cash = new_cash
    account.quantity += quantity
    account.cycle_cashflow -= debit
    account.total_fee += fee
    account.total_slippage += slip
    account.total_turnover += gross


def _sell(
    account: _Account,
    *,
    reference: Decimal,
    quantity: Decimal,
    fee_bps: Decimal,
    slippage_bps: Decimal,
    close_cycle: bool,
) -> None:
    if quantity < 0 or quantity > account.quantity:
        raise Gen2VolError("invalid sell quantity")
    if account.cycle_cashflow is None:
        raise Gen2VolError("sell outside directional cycle")
    if quantity > 0:
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            fee_rate = fee_bps / Decimal(10000)
            slip_rate = slippage_bps / Decimal(10000)
            execution = reference * (Decimal(1) - slip_rate)
            gross = quantity * execution
            fee = gross * fee_rate
            proceeds = gross - fee
            slip = quantity * (reference - execution)
        account.cash += proceeds
        account.quantity -= quantity
        account.cycle_cashflow += proceeds
        account.total_fee += fee
        account.total_slippage += slip
        account.total_turnover += gross
    if close_cycle:
        if account.quantity != 0:
            raise Gen2VolError("directional exit left residual quantity")
        account.realized.append(account.cycle_cashflow)
        account.cycle_cashflow = None


def _equity(
    account: _Account,
    *,
    mark: Decimal,
    fee_bps: Decimal,
    slippage_bps: Decimal,
) -> Decimal:
    if account.quantity == 0:
        return account.cash
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        fee_rate = fee_bps / Decimal(10000)
        slip_rate = slippage_bps / Decimal(10000)
        execution = mark * (Decimal(1) - slip_rate)
        gross = account.quantity * execution
        liquidation = gross * (Decimal(1) - fee_rate)
        return account.cash + liquidation


def _control_positions(
    *,
    signal: hsse2.SearchSeries,
    short_values,
    long_values,
) -> tuple[int, ...]:
    n = len(signal.times)
    states = [0] * n
    position = False
    for i in range(1, n):
        if i >= 2 and signal.times[i] == signal.times[i - 1] + HOUR_MS:
            vals = (
                short_values[i - 1],
                long_values[i - 1],
                short_values[i - 2],
                long_values[i - 2],
            )
            if all(math.isfinite(v) for v in vals):
                sn, ln, sp, lp = vals
                if (not position) and sn > ln and sp <= lp:
                    position = True
                elif position and sn < ln and sp >= lp:
                    position = False
        states[i] = 1 if position else 0
    return tuple(states)


def _daily_control_returns(
    *,
    exact: hsse3.ExactSeries,
    positions: Sequence[int],
    warmup_start_ms: int,
) -> dict[int, Decimal]:
    if len(positions) != len(exact.times):
        raise Gen2VolError("control-state length mismatch")
    buckets: dict[int, dict[int, Decimal]] = {}
    warmup_day = (warmup_start_ms // DAY_MS) * DAY_MS
    for i in range(1, len(exact.times)):
        t = exact.times[i]
        if t < warmup_start_ms or exact.times[i - 1] != t - HOUR_MS:
            continue
        day = (t // DAY_MS) * DAY_MS
        if day == warmup_day:
            continue
        hour = int((t - day) // HOUR_MS)
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            prev = Decimal(exact.closes[i - 1])
            now = Decimal(exact.closes[i])
            r = (now / prev) - Decimal(1) if positions[i] else Decimal(0)
        buckets.setdefault(day, {})[hour] = r

    result: dict[int, Decimal] = {}
    for day, hours in buckets.items():
        if set(hours) != set(range(24)):
            continue
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            compound = Decimal(1)
            for hour in range(24):
                compound *= Decimal(1) + hours[hour]
            result[day] = compound - Decimal(1)
    return result


def _month_start_ms(ms: int) -> int:
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    start = datetime(dt.year, dt.month, 1, tzinfo=timezone.utc)
    return int(start.timestamp() * 1000)


def _is_month_boundary(ms: int) -> bool:
    return ms == _month_start_ms(ms)


def _month_boundaries(start_ms: int, end_ms: int) -> list[int]:
    dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    current = datetime(dt.year, dt.month, 1, tzinfo=timezone.utc)
    if int(current.timestamp() * 1000) < start_ms:
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            current = datetime(current.year, current.month + 1, 1, tzinfo=timezone.utc)
    out = []
    while int(current.timestamp() * 1000) < end_ms:
        out.append(int(current.timestamp() * 1000))
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            current = datetime(current.year, current.month + 1, 1, tzinfo=timezone.utc)
    return out


def _scale_from_returns(
    daily_returns: Mapping[int, Decimal],
    *,
    boundary_ms: int,
    window_days: int = 183,
    annualization_days: int = 365,
    target: Decimal = Decimal("0.12"),
) -> Decimal:
    values = []
    for offset in range(window_days, 0, -1):
        day = boundary_ms - offset * DAY_MS
        if day not in daily_returns:
            raise Gen2VolError("incomplete 183-day volatility window")
        values.append(daily_returns[day])
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        sumsq = Decimal(0)
        for value in values:
            sumsq += value * value
        variance = Decimal(annualization_days) * sumsq / Decimal(window_days)
        if variance == 0:
            return Decimal(1)
        sigma = variance.sqrt()
        raw = target / sigma
        return min(Decimal(1), raw)


def _scale_schedule(
    *,
    exact: hsse3.ExactSeries,
    positions: Sequence[int],
    warmup_start_ms: int,
    scored_start_ms: int,
    end_ms: int,
) -> dict[int, Decimal]:
    daily = _daily_control_returns(
        exact=exact,
        positions=positions,
        warmup_start_ms=warmup_start_ms,
    )
    return {
        boundary: _scale_from_returns(daily, boundary_ms=boundary)
        for boundary in _month_boundaries(scored_start_ms, end_ms)
    }


def _simulate_cell(
    *,
    signal: hsse2.SearchSeries,
    exact: hsse3.ExactSeries,
    short_values,
    long_values,
    start_ms: int,
    end_ms: int,
    policy: Mapping[str, object],
    scaled: bool,
    scale_schedule: Mapping[int, Decimal],
) -> dict[str, object]:
    if signal.times != exact.times:
        raise Gen2VolError("signal/exact timestamps differ")
    start = bisect.bisect_left(exact.times, start_ms)
    end = bisect.bisect_left(exact.times, end_ms)
    if start >= end:
        raise Gen2VolError("Development cell is empty")
    month = _month_start_ms(exact.times[start])
    if scaled and month not in scale_schedule:
        raise Gen2VolError("missing scale at scored cell start")

    base_quantity = Decimal(str(policy["base_quantity"]))
    initial = Decimal(str(policy["initial_equity_quote"]))
    bf = Decimal(str(policy["base_fee_bps"]))
    bs = Decimal(str(policy["base_adverse_slippage_bps"]))
    sf = Decimal(str(policy["stress_fee_bps"]))
    ss = Decimal(str(policy["stress_adverse_slippage_bps"]))
    base = _new_account(initial)
    stress = _new_account(initial)

    logical_position = False
    current_scale = scale_schedule[month] if scaled else Decimal(1)
    peak = initial
    maxdd = Decimal(0)
    entry_signals = entry_fills = exit_fills = missing_fills = 0
    rebalance_count = scaled_entry_count = scale_below_one_events = 0
    active_hours = 0
    exposure_notional = Decimal(0)
    active_scales: list[Decimal] = []

    for i in range(start, end):
        close = Decimal(exact.closes[i])
        equity = _equity(base, mark=close, fee_bps=bf, slippage_bps=bs)
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
        if dd > maxdd:
            maxdd = dd
        if logical_position:
            active_hours += 1
            active_scales.append(current_scale)
            exposure_notional += base.quantity * close

        if i == 0:
            continue
        vals = (
            short_values[i],
            long_values[i],
            short_values[i - 1],
            long_values[i - 1],
        )
        if not all(math.isfinite(v) for v in vals):
            continue
        sn, ln, sp, lp = vals
        enter = (not logical_position) and sn > ln and sp <= lp
        exit_ = logical_position and sn < ln and sp >= lp
        if enter:
            entry_signals += 1

        boundary_scale = None
        if scaled and _is_month_boundary(exact.times[i]):
            if exact.times[i] not in scale_schedule:
                raise Gen2VolError("missing monthly scale")
            boundary_scale = scale_schedule[exact.times[i]]

        needs_fill = enter or exit_ or (logical_position and boundary_scale is not None)
        if not needs_fill:
            if boundary_scale is not None:
                current_scale = boundary_scale
                if current_scale < 1:
                    scale_below_one_events += 1
            continue

        fi = i + 1
        if (
            fi >= end
            or fi >= len(exact.times)
            or exact.times[fi] != exact.times[i] + HOUR_MS
        ):
            missing_fills += 1
            raise Gen2VolError("required GEN2-002 fill bar is missing")
        reference = Decimal(exact.opens[fi])
        next_scale = boundary_scale if boundary_scale is not None else current_scale

        if exit_:
            _sell(
                base, reference=reference, quantity=base.quantity,
                fee_bps=bf, slippage_bps=bs, close_cycle=True,
            )
            _sell(
                stress, reference=reference, quantity=stress.quantity,
                fee_bps=sf, slippage_bps=ss, close_cycle=True,
            )
            logical_position = False
            exit_fills += 1
            if boundary_scale is not None:
                current_scale = boundary_scale
                if current_scale < 1:
                    scale_below_one_events += 1
            continue

        if enter:
            target = base_quantity * next_scale
            _buy(
                base, reference=reference, quantity=target,
                fee_bps=bf, slippage_bps=bs, start_cycle=True,
            )
            _buy(
                stress, reference=reference, quantity=target,
                fee_bps=sf, slippage_bps=ss, start_cycle=True,
            )
            logical_position = True
            entry_fills += 1
            if next_scale < 1:
                scaled_entry_count += 1
            if boundary_scale is not None:
                current_scale = boundary_scale
                if current_scale < 1:
                    scale_below_one_events += 1
            continue

        if logical_position and boundary_scale is not None:
            target = base_quantity * boundary_scale
            delta = target - base.quantity
            if delta > 0:
                _buy(
                    base, reference=reference, quantity=delta,
                    fee_bps=bf, slippage_bps=bs, start_cycle=False,
                )
                _buy(
                    stress, reference=reference, quantity=delta,
                    fee_bps=sf, slippage_bps=ss, start_cycle=False,
                )
                rebalance_count += 1
            elif delta < 0:
                _sell(
                    base, reference=reference, quantity=-delta,
                    fee_bps=bf, slippage_bps=bs, close_cycle=False,
                )
                _sell(
                    stress, reference=reference, quantity=-delta,
                    fee_bps=sf, slippage_bps=ss, close_cycle=False,
                )
                rebalance_count += 1
            current_scale = boundary_scale
            if current_scale < 1:
                scale_below_one_events += 1

    final_mark = Decimal(exact.closes[end - 1])
    base_final = _equity(base, mark=final_mark, fee_bps=bf, slippage_bps=bs)
    stress_final = _equity(stress, mark=final_mark, fee_bps=sf, slippage_bps=ss)
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        final_dd = (peak - base_final) / peak
        base_net = base_final - initial
        stress_net = stress_final - initial
    maxdd = max(maxdd, final_dd)
    realized = hsse3._sum(base.realized)
    stress_realized = hsse3._sum(stress.realized)
    wins = [x for x in base.realized if x > 0]
    losses = [x for x in base.realized if x < 0]
    gp = hsse3._sum(wins)
    gl = -hsse3._sum(losses)
    pf_text, pf_inf, _ = hsse3._profit_factor(gp, gl)
    completed = len(base.realized)
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        expectancy = realized / Decimal(completed) if completed else Decimal(0)
        stress_expectancy = stress_realized / Decimal(completed) if completed else Decimal(0)
        mean_scale = hsse3._sum(active_scales) / Decimal(len(active_scales)) if active_scales else Decimal(1)
    median_scale = hsse3._median_decimal(active_scales) if active_scales else Decimal(1)
    min_scale = min(active_scales) if active_scales else Decimal(1)
    return {
        "base_net": base_net,
        "stress_net": stress_net,
        "realized": realized,
        "stress_realized": stress_realized,
        "maximum_drawdown": maxdd,
        "completed_trades": completed,
        "expectancy": expectancy,
        "stress_expectancy": stress_expectancy,
        "profit_factor": pf_text,
        "profit_factor_infinite": pf_inf,
        "underlying_entry_signals": entry_signals,
        "entry_fills": entry_fills,
        "exit_fills": exit_fills,
        "missing_fill_events": missing_fills,
        "monthly_rebalance_count": rebalance_count,
        "scaled_entry_count": scaled_entry_count,
        "scale_below_one_events": scale_below_one_events,
        "active_exposure_hours": active_hours,
        "exposure_notional_sum": exposure_notional,
        "mean_active_scale": mean_scale,
        "median_active_scale": median_scale,
        "minimum_active_scale": min_scale,
        "base_turnover_quote": base.total_turnover,
        "stress_turnover_quote": stress.total_turnover,
        "open_position_at_end": logical_position,
    }


def _aggregate_condition(
    *,
    survivor: Mapping[str, object],
    scaled: bool,
    folds: Sequence[Mapping[str, object]],
    signal_series: Mapping[str, hsse2.SearchSeries],
    exact_series: Mapping[str, hsse3.ExactSeries],
    cache: dict[tuple[str, str, int], object],
    scale_cache: dict[tuple[str, str, int, int], dict[int, Decimal]],
    policy: Mapping[str, object],
    warmup_start_ms: int,
    scored_start_ms: int,
    end_ms: int,
) -> dict[str, object]:
    family = str(survivor["family"])
    n1 = int(survivor["parameters"]["n1"])
    n2 = int(survivor["parameters"]["n2"])
    for symbol, series in signal_series.items():
        for window in (n1, n2):
            key = (symbol, family, window)
            if key not in cache:
                cache[key] = hsse2._indicator_series(series, family, window)

    cells = []
    nets: list[Decimal] = []
    stress_nets: list[Decimal] = []
    realized: list[Decimal] = []
    stress_realized: list[Decimal] = []
    maxdd = Decimal(0)
    completed = entry_signals = rebalances = scaled_entries = scale_events = 0
    active_hours = 0
    exposure = Decimal(0)
    all_scales: list[Decimal] = []

    for symbol in sorted(signal_series):
        scale_key = (symbol, family, n1, n2)
        if scale_key not in scale_cache:
            positions = _control_positions(
                signal=signal_series[symbol],
                short_values=cache[(symbol, family, n1)],
                long_values=cache[(symbol, family, n2)],
            )
            scale_cache[scale_key] = _scale_schedule(
                exact=exact_series[symbol],
                positions=positions,
                warmup_start_ms=warmup_start_ms,
                scored_start_ms=scored_start_ms,
                end_ms=end_ms,
            )

    for fold in folds:
        start_ms = _time_ms(fold["evaluation_start_utc"], "fold start")
        fold_end_ms = _time_ms(fold["evaluation_end_exclusive_utc"], "fold end")
        for symbol in sorted(signal_series):
            c = _simulate_cell(
                signal=signal_series[symbol],
                exact=exact_series[symbol],
                short_values=cache[(symbol, family, n1)],
                long_values=cache[(symbol, family, n2)],
                start_ms=start_ms,
                end_ms=fold_end_ms,
                policy=policy,
                scaled=scaled,
                scale_schedule=scale_cache[(symbol, family, n1, n2)],
            )
            nets.append(c["base_net"])
            stress_nets.append(c["stress_net"])
            realized.append(c["realized"])
            stress_realized.append(c["stress_realized"])
            maxdd = max(maxdd, c["maximum_drawdown"])
            completed += int(c["completed_trades"])
            entry_signals += int(c["underlying_entry_signals"])
            rebalances += int(c["monthly_rebalance_count"])
            scaled_entries += int(c["scaled_entry_count"])
            scale_events += int(c["scale_below_one_events"])
            active_hours += int(c["active_exposure_hours"])
            exposure += c["exposure_notional_sum"]
            all_scales.append(c["mean_active_scale"])
            cells.append({
                "fold_id": fold["fold_id"],
                "symbol": symbol,
                "base_net_pnl_after_costs_quote": _plain(c["base_net"]),
                "stress_net_pnl_after_costs_quote": _plain(c["stress_net"]),
                "maximum_drawdown_fraction": _plain(c["maximum_drawdown"]),
                "completed_trades": c["completed_trades"],
                "underlying_entry_signals": c["underlying_entry_signals"],
                "monthly_rebalance_count": c["monthly_rebalance_count"],
                "scaled_entry_count": c["scaled_entry_count"],
                "mean_active_scale": _plain(c["mean_active_scale"]),
                "minimum_active_scale": _plain(c["minimum_active_scale"]),
                "active_exposure_hours": c["active_exposure_hours"],
                "exposure_notional_sum": _plain(c["exposure_notional_sum"]),
            })

    total_net = hsse3._sum(nets)
    total_stress = hsse3._sum(stress_nets)
    total_realized = hsse3._sum(realized)
    total_stress_realized = hsse3._sum(stress_realized)
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        expectancy = total_realized / Decimal(completed) if completed else Decimal(0)
        stress_expectancy = total_stress_realized / Decimal(completed) if completed else Decimal(0)
        mean_scale = hsse3._sum(all_scales) / Decimal(len(all_scales)) if all_scales else Decimal(1)
    return {
        "frozen_id": survivor["frozen_id"],
        "family": family,
        "parameters": survivor["parameters"],
        "condition": "VOL_SCALED_12PCT_NO_LEVERAGE" if scaled else "CONTROL_UNSCALED",
        "base_total_net_pnl_after_costs_quote": _plain(total_net),
        "stress_total_net_pnl_after_costs_quote": _plain(total_stress),
        "base_expectancy_quote": _plain(expectancy),
        "stress_expectancy_quote": _plain(stress_expectancy),
        "maximum_drawdown_fraction": _plain(maxdd),
        "completed_trades": completed,
        "underlying_entry_signals": entry_signals,
        "monthly_rebalance_count": rebalances,
        "scaled_entry_count": scaled_entries,
        "scale_below_one_events": scale_events,
        "active_exposure_hours": active_hours,
        "exposure_notional_sum": _plain(exposure),
        "mean_active_scale": _plain(mean_scale),
        "cells": cells,
    }


def _write_result(root: Path, record: Mapping[str, object]) -> tuple[str, str]:
    payload = _canonical_json(record)
    digest = _sha256(payload)
    safe = root.resolve()
    out = safe / "generation-2" / "gen2-002"
    out.mkdir(parents=True, exist_ok=True)
    path = out / ("vol-scaling-" + digest[:24] + ".json")
    if path.exists():
        if path.read_bytes() != payload:
            raise Gen2VolError("existing GEN2-002 artifact differs")
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    return path.relative_to(safe).as_posix(), digest


def run(*, runtime_root: Path, protocol_path: Path = DEFAULT_PROTOCOL_PATH) -> dict[str, object]:
    protocol, protocol_sha, freeze, _ = validate_protocol(protocol_path)
    q = protocol["bindings"]["development_quality_manifest"]
    try:
        corpus = controls._load_control_corpus(
            runtime_root=runtime_root,
            quality_manifest_relative_path=q["relative_path"],
            quality_manifest_file_sha256=q["file_sha256"],
        )
    except controls.ControlError as exc:
        raise Gen2VolError(str(exc)) from None
    if corpus.event_id != "CRL-CONTROL-DEV-POOL-001":
        raise Gen2VolError("wrong Development corpus")

    signal_series = {}
    exact_series = {}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        signal_series[symbol], exact_series[symbol] = _series(corpus, symbol)

    scope = protocol["development_scope"]
    folds = scope["development_folds"]
    warmup_start_ms = _time_ms(scope["estimator_warmup_start_utc"], "warmup start")
    scored_start_ms = _time_ms(scope["scored_analysis_start_utc"], "scored start")
    end_ms = _time_ms(scope["analysis_end_exclusive_utc"], "analysis end")
    policy = protocol["execution"]
    cache: dict[tuple[str, str, int], object] = {}
    scale_cache: dict[tuple[str, str, int, int], dict[int, Decimal]] = {}

    controls_by_id = {}
    scaled_by_id = {}
    for survivor in freeze["survivors"]:
        controls_by_id[survivor["frozen_id"]] = _aggregate_condition(
            survivor=survivor,
            scaled=False,
            folds=folds,
            signal_series=signal_series,
            exact_series=exact_series,
            cache=cache,
            scale_cache=scale_cache,
            policy=policy,
            warmup_start_ms=warmup_start_ms,
            scored_start_ms=scored_start_ms,
            end_ms=end_ms,
        )
        scaled_by_id[survivor["frozen_id"]] = _aggregate_condition(
            survivor=survivor,
            scaled=True,
            folds=folds,
            signal_series=signal_series,
            exact_series=exact_series,
            cache=cache,
            scale_cache=scale_cache,
            policy=policy,
            warmup_start_ms=warmup_start_ms,
            scored_start_ms=scored_start_ms,
            end_ms=end_ms,
        )

    base_deltas = []
    stress_deltas = []
    dd_deltas = []
    aggregate_scaled_base = Decimal(0)
    aggregate_control_base = Decimal(0)
    aggregate_scaled_stress = Decimal(0)
    aggregate_control_stress = Decimal(0)
    activated_refs = event_total = nonworse_dd = 0
    opportunity_failures = []
    comparison_rows = []

    for survivor in freeze["survivors"]:
        fid = survivor["frozen_id"]
        control = controls_by_id[fid]
        scaled = scaled_by_id[fid]
        cbase = Decimal(control["base_total_net_pnl_after_costs_quote"])
        sbase = Decimal(scaled["base_total_net_pnl_after_costs_quote"])
        cstress = Decimal(control["stress_total_net_pnl_after_costs_quote"])
        sstress = Decimal(scaled["stress_total_net_pnl_after_costs_quote"])
        cdd = Decimal(control["maximum_drawdown_fraction"])
        sdd = Decimal(scaled["maximum_drawdown_fraction"])
        base_deltas.append(sbase - cbase)
        stress_deltas.append(sstress - cstress)
        dd_deltas.append(sdd - cdd)
        aggregate_control_base += cbase
        aggregate_scaled_base += sbase
        aggregate_control_stress += cstress
        aggregate_scaled_stress += sstress
        if int(scaled["scale_below_one_events"]) > 0:
            activated_refs += 1
        event_total += int(scaled["scaled_entry_count"]) + int(scaled["monthly_rebalance_count"])
        if sdd <= cdd:
            nonworse_dd += 1

        cactive = int(control["active_exposure_hours"])
        sactive = int(scaled["active_exposure_hours"])
        cexp = Decimal(control["exposure_notional_sum"])
        sexp = Decimal(scaled["exposure_notional_sum"])
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            active_ratio = Decimal(sactive) / Decimal(cactive) if cactive else Decimal(1)
            notional_ratio = sexp / cexp if cexp else Decimal(1)
        reasons = []
        if scaled["underlying_entry_signals"] != control["underlying_entry_signals"]:
            reasons.append("DIRECTIONAL_ENTRY_SIGNAL_COUNT_CHANGED")
        if scaled["completed_trades"] != control["completed_trades"]:
            reasons.append("COMPLETED_DIRECTIONAL_TRADE_COUNT_CHANGED")
        if active_ratio < Decimal("1.0"):
            reasons.append("ACTIVE_EXPOSURE_HOURS_STARVED")
        if notional_ratio < Decimal("0.25"):
            reasons.append("NOTIONAL_EXPOSURE_STARVED")
        if reasons:
            opportunity_failures.append(fid)
        comparison_rows.append({
            "frozen_id": fid,
            "base_net_delta_quote": _plain(sbase - cbase),
            "stress_net_delta_quote": _plain(sstress - cstress),
            "drawdown_delta_fraction": _plain(sdd - cdd),
            "active_exposure_hours_ratio_vs_control": _plain(active_ratio),
            "notional_exposure_ratio_vs_control": _plain(notional_ratio),
            "opportunity_preservation_status": "PASS" if not reasons else "FAIL",
            "opportunity_failure_reasons": reasons,
        })

    median_base = hsse3._median_decimal(base_deltas)
    median_stress = hsse3._median_decimal(stress_deltas)
    median_dd = hsse3._median_decimal(dd_deltas)
    g = protocol["proposal_gate"]
    failure_reasons = []
    if activated_refs < int(g["minimum_reference_strategies_with_scale_below_one"]):
        failure_reasons.append("SCALER_ACTIVATION_REFERENCE_COUNT")
    if event_total < int(g["minimum_scaled_entry_or_rebalance_events_total"]):
        failure_reasons.append("SCALER_ACTIVATION_EVENT_COUNT")
    if opportunity_failures:
        failure_reasons.append("OPPORTUNITY_PRESERVATION_FAILED")
    if aggregate_scaled_base <= 0:
        failure_reasons.append("AGGREGATE_SCALED_BASE_NET_NOT_POSITIVE")
    if aggregate_scaled_stress <= 0:
        failure_reasons.append("AGGREGATE_SCALED_STRESS_NET_NOT_POSITIVE")
    if aggregate_scaled_base <= aggregate_control_base:
        failure_reasons.append("AGGREGATE_BASE_NET_NOT_IMPROVED")
    if aggregate_scaled_stress <= aggregate_control_stress:
        failure_reasons.append("AGGREGATE_STRESS_NET_NOT_IMPROVED")
    if median_base <= 0:
        failure_reasons.append("MEDIAN_BASE_NET_DELTA_NOT_POSITIVE")
    if median_stress <= 0:
        failure_reasons.append("MEDIAN_STRESS_NET_DELTA_NOT_POSITIVE")
    if median_dd >= 0:
        failure_reasons.append("MEDIAN_DRAWDOWN_DELTA_NOT_NEGATIVE")
    if nonworse_dd < int(g["at_least_reference_strategies_with_nonworse_drawdown"]):
        failure_reasons.append("NONWORSE_DRAWDOWN_REFERENCE_COUNT")

    status = "PASS" if not failure_reasons else "FAIL"
    record = {
        "schema": "YATL_GEN2_VOL_SCALING_RESULT",
        "schema_version": SCHEMA_VERSION,
        "implementation_id": IMPLEMENTATION_ID,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha,
        "source_candidate_id": "RIE-CAND-0025",
        "tested_object_id": "GEN2-ADAPT-0002-VOL-SCALING",
        "tested_object_type": "YATL_INTERNAL_ADAPTATION",
        "source_candidate_claimed_reproduced": False,
        "source_performance_claims_used_as_evidence": False,
        "development_corpus_id": "CRL-CONTROL-DEV-POOL-001",
        "condition_count": 12,
        "status": status,
        "proposal_count": 1 if status == "PASS" else 0,
        "proposal_ids": ["GEN2-ADAPT-0002-VOL-SCALING"] if status == "PASS" else [],
        "failure_reasons": failure_reasons,
        "activated_reference_strategies": activated_refs,
        "scaled_entry_or_rebalance_events_total": event_total,
        "reference_strategies_with_nonworse_drawdown": nonworse_dd,
        "aggregate_scaled_base_net_quote": _plain(aggregate_scaled_base),
        "aggregate_control_base_net_quote": _plain(aggregate_control_base),
        "aggregate_scaled_stress_net_quote": _plain(aggregate_scaled_stress),
        "aggregate_control_stress_net_quote": _plain(aggregate_control_stress),
        "median_base_net_delta_quote": _plain(median_base),
        "median_stress_net_delta_quote": _plain(median_stress),
        "median_drawdown_delta_fraction": _plain(median_dd),
        "opportunity_failure_reference_ids": opportunity_failures,
        "comparisons": comparison_rows,
        "control_conditions": [controls_by_id[x["frozen_id"]] for x in freeze["survivors"]],
        "scaled_conditions": [scaled_by_id[x["frozen_id"]] for x in freeze["survivors"]],
        "hsse_004b_2023_2024_read": False,
        "hsse_005_outcomes_used_for_selection": False,
        "fresh_oos_read": False,
        "recent_reserve_read": False,
        "reranking_performed": False,
        "retuning_performed": False,
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p11_locked": True,
    }
    artifact_rel, artifact_sha = _write_result(runtime_root, record)
    return {
        "implementation_id": IMPLEMENTATION_ID,
        "protocol_sha256": protocol_sha,
        "condition_count": 12,
        "status": status,
        "proposal_count": record["proposal_count"],
        "proposal_ids": record["proposal_ids"],
        "artifact_relative_path": artifact_rel,
        "artifact_file_sha256": artifact_sha,
        "fresh_oos_read": False,
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)
    parser.add_argument("--validate-protocol-only", action="store_true")
    args = parser.parse_args(argv)
    if args.validate_protocol_only:
        protocol, sha, freeze, _ = validate_protocol(args.protocol)
        print(_json({
            "implementation_id": IMPLEMENTATION_ID,
            "protocol_id": protocol["protocol_id"],
            "protocol_sha256": sha,
            "survivor_count": len(freeze["survivors"]),
            "condition_count": protocol["trial_matrix"]["total_conditions"],
            "performance_run_executed": False,
            "research_only": True,
            "p10_write_allowed": False,
            "p11_locked": True,
        }))
        return 0
    if args.runtime_root is None:
        parser.error("--runtime-root is required unless --validate-protocol-only is used")
    print(_json(run(runtime_root=args.runtime_root, protocol_path=args.protocol)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
