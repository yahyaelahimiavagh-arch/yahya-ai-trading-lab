"""YATL-PREREG-VOL-SCALE-001 Minimal Local Implementation and Two-Arm Runner.

Compares frozen HSSE004A-SURV-002 EMA(11, 491) fixed sizing against unchanged
source-style total-volatility position sizing without leverage.

Strictly research-only. Evaluates only on the two specified arms across
BTCUSDT and ETHUSDT. Does not modify canonical protocols or access protected data.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from functools import wraps
from pathlib import Path
from typing import Any, Mapping, Sequence

from research.crisis_lab import controls
from research.generation_2 import downside_vol_scaling as g
from research.generation_2 import vol_scaling as shared
from research.historical_strategy_search import survivor_ranking as hsse3
from research.historical_strategy_search import trend_ma as hsse2
from yatl.backtest.costs import DECIMAL_PRECISION

IMPLEMENTATION_ID = "YATL-VOL-SCALE-PREREG/0.1.0"
PROTOCOL_SHA256 = "fc2011f86ea47b86e12b4f77976b443ad56871193f9b585a5315ea191cca0bb2"
DEFAULT_PROTOCOL_PATH = (
    shared.REPO_ROOT / "docs/research/generation-2/YATL-PREREG-VOL-SCALE-001.json"
)
CONDITIONS = (
    "CONTROL_UNSCALED",
    "SOURCE_STYLE_TOTAL_VOL_SCALED_NO_LEVERAGE",
)
UNIVERSE = ("BTCUSDT", "ETHUSDT")
CANDIDATE_ID = "EXP-VOL-SCALE-001"
FROZEN_ID = "HSSE004A-SURV-002"
FAST_PERIOD = 11
SLOW_PERIOD = 491
MIN_TRADES_THRESHOLD = 30
ONE = Decimal(1)
ZERO = Decimal(0)

UNIMPLEMENTED_BENCHMARKS_AND_RISK_METRICS = {
    "cash_matched_benchmark": "PENDING_IMPLEMENTATION_BLOCKER",
    "exposure_matched_buy_and_hold_benchmark": "PENDING_IMPLEMENTATION_BLOCKER",
    "per_period_sharpe_ratio": "PENDING_IMPLEMENTATION_BLOCKER",
    "per_period_sortino_ratio": "PENDING_IMPLEMENTATION_BLOCKER",
}


class VolScalePreregError(RuntimeError):
    """Protocol validation or execution boundary violation."""


def _exact(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            return fn(*args, **kwargs)

    return wrapper


def _read_normalized(path: Path) -> bytes:
    """Read file bytes, normalizing CRLF to LF for cross-platform hash stability."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def _git_blob_sha(payload: bytes) -> str:
    header = b"blob " + str(len(payload)).encode("ascii") + b"\0"
    return hashlib.sha1(header + payload).hexdigest()


def _read_repo_bound(
    binding: Mapping[str, object], label: str
) -> tuple[dict[str, Any], bytes]:
    relative = binding.get("relative_path")
    expected = binding.get("git_blob_sha")
    if (
        not isinstance(relative, str)
        or not isinstance(expected, str)
        or len(expected) != 40
    ):
        raise VolScalePreregError(f"{label} binding is invalid")
    target = (shared.REPO_ROOT / relative).resolve()
    if not target.is_relative_to(shared.REPO_ROOT.resolve()) or target.is_symlink():
        raise VolScalePreregError(f"{label} path is unsafe")
    try:
        payload = _read_normalized(target)
    except OSError:
        raise VolScalePreregError(f"cannot read {label}") from None
    if not payload or len(payload) > shared.MAX_BOUND_BYTES:
        raise VolScalePreregError(f"{label} size is invalid")
    if _git_blob_sha(payload) != expected:
        raise VolScalePreregError(f"{label} Git blob binding mismatch")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise VolScalePreregError(f"{label} is not UTF-8 JSON") from None
    if not isinstance(record, dict):
        raise VolScalePreregError(f"{label} must be an object")
    return record, payload


def validate_protocol(
    path: Path = DEFAULT_PROTOCOL_PATH,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Validate protocol integrity, SHA-256 digest, and bound artifacts."""
    target = path.resolve()
    if not target.is_relative_to(shared.REPO_ROOT.resolve()) or target.is_symlink():
        raise VolScalePreregError("unsafe protocol path")
    try:
        payload = _read_normalized(target)
    except OSError:
        raise VolScalePreregError("protocol unreadable") from None
    digest = hashlib.sha256(payload).hexdigest()
    if digest != PROTOCOL_SHA256:
        raise VolScalePreregError(
            f"YATL-PREREG-VOL-SCALE-001 frozen protocol SHA-256 mismatch: expected {PROTOCOL_SHA256}, got {digest}"
        )
    p = json.loads(payload.decode("utf-8"))

    # Validate identity and safety invariants
    if (
        p.get("schema") != "YATL_VOL_SCALE_PREREG_PROTOCOL"
        or p.get("protocol_id") != "YATL-PREREG-VOL-SCALE-001"
        or p.get("candidate_id") != CANDIDATE_ID
        or p.get("trial_matrix", {}).get("conditions") != list(CONDITIONS)
        or p.get("safety_boundary", {}).get("p10_read") is not False
        or p.get("safety_boundary", {}).get("p10_write_allowed") is not False
        or p.get("safety_boundary", {}).get("p11_locked") is not True
        or p.get("safety_boundary", {}).get("live_master_lock") != "OFF"
        or p.get("safety_boundary", {}).get("paper_research_only") is not True
    ):
        raise VolScalePreregError("protocol identity or safety mismatch")

    # Validate bound files
    bound = {}
    for label in ("survivor_freeze", "gen2_downside_protocol"):
        bound[label], _ = _read_repo_bound(p["bindings"][label], label)

    freeze = bound["survivor_freeze"]
    survivors = {s["frozen_id"]: s for s in freeze.get("survivors", [])}
    if FROZEN_ID not in survivors:
        raise VolScalePreregError(f"candidate {FROZEN_ID} not in bound survivor freeze")

    surv = survivors[FROZEN_ID]
    if (
        surv.get("family") != "TREND_MA_EMA"
        or surv.get("parameters", {}).get("n1") != FAST_PERIOD
        or surv.get("parameters", {}).get("n2") != SLOW_PERIOD
    ):
        raise VolScalePreregError("survivor parameter mismatch")

    return p, digest, freeze


def check_execution_prerequisites(
    protocol_path: Path = DEFAULT_PROTOCOL_PATH,
    *,
    allow_market_data: bool = False,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Mandatory protocol validation and safety barrier check.

    Must be called before any execution path. Fails closed if market data
    execution is attempted while under protocol freeze.
    """
    p, sha, freeze = validate_protocol(protocol_path)

    # Enforce immutable safety boundary
    sb = p.get("safety_boundary", {})
    if (
        sb.get("p10_read") is not False
        or sb.get("p10_write_allowed") is not False
        or sb.get("p11_locked") is not True
        or sb.get("live_master_lock") != "OFF"
        or sb.get("paper_research_only") is not True
        or sb.get("holdout_read_forbidden") is not True
        or sb.get("fresh_oos_read_forbidden") is not True
        or sb.get("recent_reserve_read_forbidden") is not True
    ):
        raise VolScalePreregError("Safety boundary invariant violated in protocol")

    # Scope check: market data execution remains locked
    if allow_market_data or not sb.get("paper_research_only"):
        raise VolScalePreregError(
            "Market data execution path is currently disabled. "
            "Requires explicit protocol authorization and unlock."
        )

    return p, sha, freeze


def load_market_data(*args, **kwargs) -> Any:
    """Explicitly disabled entry point for market data loading."""
    raise VolScalePreregError(
        "Market data loading is disabled and locked in Sprint 03. "
        "Direct helper and CLI execution may only use synthetic fixtures."
    )


@_exact
def run_two_arm_single_symbol(
    *,
    signal: hsse2.SearchSeries,
    exact: hsse3.ExactSeries,
    warmup_start_ms: int,
    first_managed_ms: int,
    scored_start_ms: int,
    end_ms: int,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Execute both Arm A and Arm B on a single symbol series.

    Pure mathematical calculation helper operating on in-memory SearchSeries
    and ExactSeries structures. It accepts in-memory series regardless of
    provenance and does not distinguish synthetic from historical series by
    object type alone.

    Market-data CLI execution and file loading remain disabled under protocol
    freeze. In Sprint 03, only synthetic fixtures are evaluated.
    """
    if signal.times != exact.times:
        raise VolScalePreregError("signal and exact series timestamps differ")

    # 1. Compute EMA indicators for candidate (11, 491)
    short_values = hsse2._indicator_series(signal, "TREND_MA_EMA", FAST_PERIOD)
    long_values = hsse2._indicator_series(signal, "TREND_MA_EMA", SLOW_PERIOD)

    # 2. Derive control positions across warmup and scored periods
    positions = shared._control_positions(
        signal=signal,
        short_values=short_values,
        long_values=long_values,
        reset_ms=warmup_start_ms,
    )

    # 3. Derive monthly inputs and identify exposed gap days
    months, exposed_days = g._monthly_inputs(
        exact=exact,
        positions=positions,
        start_ms=warmup_start_ms,
        end_ms=end_ms,
    )

    # 4. Compute monthly volatility estimators
    estimators = g._estimators(months)

    # 5. Expanding schedule for source-style total-volatility scaler
    schedules, counters = g._schedule(
        months=months,
        estimators=estimators,
        first_managed_ms=first_managed_ms,
        scored_start_ms=scored_start_ms,
        end_ms=end_ms,
        minimum_pairs=6,
    )
    total_schedule = dict(schedules["total"])
    total_counts = counters["total"]

    start_idx = bisect.bisect_left(exact.times, scored_start_ms)
    if start_idx < len(exact.times):
        start_month = shared._month_start_ms(exact.times[start_idx])
        if start_month not in total_schedule:
            total_schedule[start_month] = {"scale": ONE, "new": False}

    # 6. Simulate Arm A: CONTROL_UNSCALED
    res_control = g._simulate_cell(
        signal=signal,
        exact=exact,
        short_values=short_values,
        long_values=long_values,
        start_ms=scored_start_ms,
        end_ms=end_ms,
        policy=policy,
        decisions={},
        condition=CONDITIONS[0],
    )

    # 7. Simulate Arm B: SOURCE_STYLE_TOTAL_VOL_SCALED_NO_LEVERAGE
    res_scaled = g._simulate_cell(
        signal=signal,
        exact=exact,
        short_values=short_values,
        long_values=long_values,
        start_ms=scored_start_ms,
        end_ms=end_ms,
        policy=policy,
        decisions=total_schedule,
        condition=CONDITIONS[1],
    )

    # 8. Enrich with transparent exposure metrics and evidence classification
    def enrich_arm(cell: dict[str, Any], is_scaled: bool) -> dict[str, Any]:
        out = dict(cell)
        act_hours = out["active_hours"]
        notional_exp = out["notional_exposure"]
        base_net = out["base_net"]
        stress_net = out["stress_net"]
        completed = out["completed_trades"]

        avg_notional = (
            notional_exp / Decimal(act_hours) if act_hours > 0 else ZERO
        )
        pnl_over_avg_notional_base = (
            base_net / avg_notional if avg_notional > ZERO else ZERO
        )
        pnl_over_avg_notional_stress = (
            stress_net / avg_notional if avg_notional > ZERO else ZERO
        )

        out["symbol"] = signal.symbol
        out["average_active_notional_quote"] = avg_notional
        out["pnl_over_average_active_notional_base"] = pnl_over_avg_notional_base
        exp = cell.get("expectancy_base") if "expectancy_base" in cell else cell.get("expectancy")
        if exp is not None:
            out["expectancy_base"] = exp

        pf = cell.get("profit_factor_base") if "profit_factor_base" in cell else cell.get("profit_factor")
        if pf is not None:
            out["profit_factor_base"] = pf

        dd = cell.get("maximum_drawdown") if "maximum_drawdown" in cell else cell.get("drawdown")
        if dd is not None:
            out["maximum_drawdown"] = dd
        out["evidence_status"] = (
            "SUFFICIENT_EVIDENCE"
            if completed >= MIN_TRADES_THRESHOLD
            else "INSUFFICIENT_EVIDENCE"
        )
        out["unimplemented_evaluations"] = dict(
            UNIMPLEMENTED_BENCHMARKS_AND_RISK_METRICS
        )
        return out

    arm_a = enrich_arm(res_control, is_scaled=False)
    arm_b = enrich_arm(res_scaled, is_scaled=True)

    # Ratios vs control
    ctrl_hours = arm_a["active_hours"]
    ctrl_notional = arm_a["notional_exposure"]
    arm_b["active_exposure_hours_fraction_vs_control"] = (
        Decimal(arm_b["active_hours"]) / Decimal(ctrl_hours)
        if ctrl_hours > 0
        else ONE
    )
    arm_b["notional_exposure_ratio_vs_control"] = (
        arm_b["notional_exposure"] / ctrl_notional if ctrl_notional > ZERO else ONE
    )

    # Deltas (Arm B minus Arm A)
    deltas = {
        "symbol": signal.symbol,
        "delta_base_net": arm_b["base_net"] - arm_a["base_net"],
        "delta_drawdown": (
            (arm_b.get("maximum_drawdown", arm_b.get("drawdown")) - arm_a.get("maximum_drawdown", arm_a.get("drawdown")))
            if arm_b.get("maximum_drawdown", arm_b.get("drawdown")) is not None
            and arm_a.get("maximum_drawdown", arm_a.get("drawdown")) is not None
            else None
        ),
        "delta_pnl_over_average_active_notional_base": (
            arm_b["pnl_over_average_active_notional_base"]
            - arm_a["pnl_over_average_active_notional_base"]
        ),
        "delta_rebalances": arm_b["rebalances"],
        "delta_rebalance_notional": arm_b["rebalance_notional"],
    }

    return {
        "symbol": signal.symbol,
        "arm_a_control": arm_a,
        "arm_b_scaled": arm_b,
        "deltas": deltas,
        "decision_counts": total_counts,
        "exposed_gap_days": exposed_days,
    }


def _finite(value: object) -> bool:
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, dict):
        return all(_finite(v) for v in value.values())
    if isinstance(value, (tuple, list)):
        return all(_finite(v) for v in value)
    return True


@_exact
def adjudicate_universe(
    symbol_evaluations: Mapping[str, Mapping[str, Any]],
    protocol: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine separate symbol results and adjudicate preregistered gates.

    Binds economic checks strictly to the canonical protocol from disk.
    Independently validates the on-disk protocol and rejects any altered
    in-memory protocol even when schema and IDs match.
    Never returns PASS or proposal_count=1 while evaluation blockers remain.
    """
    canonical_protocol, canonical_sha, _ = validate_protocol(DEFAULT_PROTOCOL_PATH)

    if protocol is not None:
        if not isinstance(protocol, dict):
            raise VolScalePreregError("protocol must be a dictionary")
        canonical_serialized = json.dumps(canonical_protocol, sort_keys=True)
        in_memory_serialized = json.dumps(protocol, sort_keys=True)
        if canonical_serialized != in_memory_serialized:
            raise VolScalePreregError(
                "Altered in-memory protocol rejected: does not match canonical frozen protocol on disk"
            )
    effective_protocol = canonical_protocol

    gates = effective_protocol.get("evidence_and_gates", {})
    min_trades = gates.get("min_completed_trades_threshold", MIN_TRADES_THRESHOLD)
    min_valid_fraction = Decimal(str(gates.get("minimum_valid_new_scale_decision_fraction", "0.50")))
    unimplemented_dict = gates.get("unimplemented_benchmarks_and_risk_metrics", {})

    symbols = list(symbol_evaluations.keys())
    if set(symbols) != set(UNIVERSE):
        raise VolScalePreregError(
            f"evaluated universe mismatch: expected {set(UNIVERSE)}, got {set(symbols)}"
        )

    # Verify presence and finiteness of mandatory metrics on all symbols and arms
    missing_metrics = []
    for s in symbols:
        for arm_key in ("arm_a_control", "arm_b_scaled"):
            cell = symbol_evaluations[s].get(arm_key, {})
            for m in (
                "expectancy_base",
                "profit_factor_base",
                "base_net",
                "stress_net",
                "maximum_drawdown",
                "average_active_notional_quote",
                "pnl_over_average_active_notional_base",
            ):
                if m not in cell or cell[m] is None:
                    missing_metrics.append(f"MISSING_MANDATORY_METRIC:{s}:{arm_key}:{m}")
                elif isinstance(cell[m], Decimal) and not cell[m].is_finite():
                    missing_metrics.append(f"NONFINITE_MANDATORY_METRIC:{s}:{arm_key}:{m}")

    # Aggregate summaries for Arm A and Arm B
    def aggregate_arm(arm_key: str) -> dict[str, Any]:
        cells = [symbol_evaluations[s][arm_key] for s in symbols]
        completed = sum(c.get("completed_trades", 0) for c in cells)
        signals = sum(c.get("entry_signals", 0) for c in cells)
        net_base = sum((c.get("base_net", ZERO) for c in cells), ZERO)
        net_stress = sum((c.get("stress_net", ZERO) for c in cells), ZERO)
        max_dd = max((c.get("maximum_drawdown", c.get("drawdown", ZERO)) for c in cells), default=ZERO)
        rebalances = sum(c.get("rebalances", 0) for c in cells)
        reb_notional = sum((c.get("rebalance_notional", ZERO) for c in cells), ZERO)
        scaled_entries = sum(c.get("scaled_entries", 0) for c in cells)
        active_hours = sum(c.get("active_hours", 0) for c in cells)
        notional_exp = sum((c.get("notional_exposure", ZERO) for c in cells), ZERO)
        avg_notional = (
            notional_exp / Decimal(active_hours) if active_hours > 0 else ZERO
        )
        pnl_norm_base = (
            net_base / avg_notional if avg_notional > ZERO else ZERO
        )
        pnl_norm_stress = (
            net_stress / avg_notional if avg_notional > ZERO else ZERO
        )

        return {
            "completed_trades": completed,
            "entry_signals": signals,
            "base_net": net_base,
            "stress_net": net_stress,
            "maximum_drawdown": max_dd,
            "rebalances": rebalances,
            "rebalance_notional": reb_notional,
            "scaled_entries": scaled_entries,
            "active_hours": active_hours,
            "notional_exposure": notional_exp,
            "average_active_notional_quote": avg_notional,
            "pnl_over_average_active_notional_base": pnl_norm_base,
            "pnl_over_average_active_notional_stress": pnl_norm_stress,
            "evidence_status": (
                "SUFFICIENT_EVIDENCE"
                if completed >= min_trades * len(symbols)
                else "INSUFFICIENT_EVIDENCE"
            ),
        }

    agg_a = aggregate_arm("arm_a_control")
    agg_b = aggregate_arm("arm_b_scaled")

    # Decision counts & zero decision handling
    total_valid_decisions = sum(
        symbol_evaluations[s].get("decision_counts", {}).get("valid_new_scale_decisions", 0)
        for s in symbols
    )
    total_decisions = sum(
        symbol_evaluations[s].get("decision_counts", {}).get("valid_new_scale_decisions", 0)
        + symbol_evaluations[s].get("decision_counts", {}).get("carried_scale_decisions", 0)
        for s in symbols
    )

    zero_decisions = total_decisions == 0
    if zero_decisions:
        valid_scale_fraction = ZERO
    else:
        valid_scale_fraction = Decimal(total_valid_decisions) / Decimal(total_decisions)

    # Opportunity preservation checks
    opp_failures = []
    if agg_b["entry_signals"] != agg_a["entry_signals"]:
        opp_failures.append("DIRECTIONAL_ENTRY_SIGNAL_COUNT_CHANGED")
    if agg_b["completed_trades"] != agg_a["completed_trades"]:
        opp_failures.append("COMPLETED_DIRECTIONAL_TRADE_COUNT_CHANGED")

    active_ratio = (
        Decimal(agg_b["active_hours"]) / Decimal(agg_a["active_hours"])
        if agg_a["active_hours"] > 0
        else ONE
    )
    if active_ratio < ONE:
        opp_failures.append("ACTIVE_EXPOSURE_HOURS_STARVED")

    notional_ratio = (
        agg_b["notional_exposure"] / agg_a["notional_exposure"]
        if agg_a["notional_exposure"] > ZERO
        else ONE
    )
    if notional_ratio < Decimal("0.25"):
        opp_failures.append("NOTIONAL_EXPOSURE_STARVED")

    # Scaler activation check
    scaler_activated = (
        agg_b["scaled_entries"] > 0
        or agg_b["rebalances"] > 0
        or any(
            symbol_evaluations[s]["arm_b_scaled"].get("minimum_scale", ONE) < ONE
            for s in symbols
        )
    )

    # Preregistered proposal gate checks
    gate_failures = list(opp_failures)
    gate_failures.extend(missing_metrics)

    if zero_decisions:
        gate_failures.append("ZERO_SCALE_DECISIONS_EVALUATED")
    elif valid_scale_fraction < min_valid_fraction:
        gate_failures.append("VALID_SCALE_DECISION_FRACTION_LOW")

    if not scaler_activated:
        gate_failures.append("SCALER_NEVER_ACTIVATED")
    if agg_b["base_net"] <= ZERO:
        gate_failures.append("AGGREGATE_BASE_NOT_POSITIVE")
    if agg_b["stress_net"] <= ZERO:
        gate_failures.append("AGGREGATE_STRESS_NOT_POSITIVE")
    if agg_b["base_net"] <= agg_a["base_net"]:
        gate_failures.append("BASE_NET_NOT_ABOVE_CONTROL")
    if agg_b["stress_net"] <= agg_a["stress_net"]:
        gate_failures.append("STRESS_NET_NOT_ABOVE_CONTROL")
    if agg_b["maximum_drawdown"] > agg_a["maximum_drawdown"]:
        gate_failures.append("DRAWDOWN_WORSE_THAN_CONTROL")
    if not (_finite(agg_a) and _finite(agg_b)):
        gate_failures.append("NONFINITE_METRICS")

    # Per-symbol trade sufficiency checks
    insufficient_symbols = [
        s
        for s in symbols
        if symbol_evaluations[s]["arm_a_control"].get("completed_trades", 0) < min_trades
    ]

    # Evaluation blockers
    blockers = [
        f"UNRESOLVED_EVALUATION_BLOCKER:{k}"
        for k, v in unimplemented_dict.items()
        if "BLOCKER" in str(v)
    ]

    # Aggregate deltas
    agg_deltas = {
        "delta_base_net": agg_b["base_net"] - agg_a["base_net"],
        "delta_stress_net": agg_b["stress_net"] - agg_a["stress_net"],
        "delta_drawdown": agg_b["maximum_drawdown"] - agg_a["maximum_drawdown"],
        "delta_pnl_over_average_active_notional_base": (
            agg_b["pnl_over_average_active_notional_base"]
            - agg_a["pnl_over_average_active_notional_base"]
        ),
        "active_exposure_hours_fraction_vs_control": active_ratio,
        "notional_exposure_ratio_vs_control": notional_ratio,
        "valid_scale_decision_fraction": valid_scale_fraction,
    }

    # Strict economic verdict: Never return PASS while blockers remain!
    verdict_reasons = list(gate_failures)
    if insufficient_symbols or zero_decisions:
        status = "INSUFFICIENT_EVIDENCE"
        if insufficient_symbols:
            verdict_reasons.append(
                f"INSUFFICIENT_TRADES: completed < {min_trades} on {', '.join(insufficient_symbols)}"
            )
    elif gate_failures:
        status = "FAIL"
    elif blockers:
        status = "BLOCKED"
        verdict_reasons.extend(blockers)
    else:
        status = "PASS"

    proposal_count = 1 if status == "PASS" else 0

    return {
        "status": status,
        "proposal_count": proposal_count,
        "implementation_readiness": "READY_FOR_INDEPENDENT_REVIEW",
        "economic_qualification": status,
        "verdict_reasons": verdict_reasons,
        "blockers": blockers,
        "aggregate_arm_a_control": agg_a,
        "aggregate_arm_b_scaled": agg_b,
        "aggregate_deltas": agg_deltas,
        "symbols": symbols,
        "unimplemented_evaluations": dict(unimplemented_dict),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="YATL-PREREG-VOL-SCALE-001 Research Protocol Runner"
    )
    parser.add_argument(
        "--validate-protocol-only",
        action="store_true",
        help="Validate protocol SHA-256 and safety bindings without reading market data",
    )
    parser.add_argument(
        "--paper-only",
        action="store_true",
        default=True,
        help="Enforce paper research boundary",
    )
    args = parser.parse_args(argv)

    # Mandatory protocol validation and scope verification upfront
    p, sha, freeze = check_execution_prerequisites(
        DEFAULT_PROTOCOL_PATH, allow_market_data=False
    )

    if args.validate_protocol_only:
        print(f"PROTOCOL VALIDATION: PASS (id={p['protocol_id']}, sha={sha})")
        return 0

    print(
        "Execution on market data is currently disabled by protocol freeze. "
        "Only synthetic validation and --validate-protocol-only are permitted."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
