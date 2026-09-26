"""Generation-2 standalone stop-loss overlay Development runner.

Research only. Consumes the already-exposed CRL Development corpus and the
immutable HSSE-004A survivor set. It never reads 2023-2024 Blind outcomes,
2025-2026 Fresh OOS, recent reserve, P10 state, credentials, accounts or orders.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Mapping, Sequence

from research.crisis_lab import controls
from research.historical_strategy_search import survivor_ranking as hsse3
from research.historical_strategy_search import trend_ma as hsse2
from yatl.data import INTERVAL_MILLISECONDS

IMPLEMENTATION_ID = "GEN2-001-STOP-OVERLAY/0.1.0"
SCHEMA_VERSION = "0.1.0"
HOUR_MS = INTERVAL_MILLISECONDS["1h"]
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROTOCOL_PATH = REPO_ROOT / (
    "docs/research/generation-2/"
    "GEN2-001-STOP-OVERLAY-PROTOCOL-v0.1.0.json"
)
MAX_PROTOCOL_BYTES = 2 * 1024 * 1024
MAX_BOUND_BYTES = 4 * 1024 * 1024


class Gen2StopError(RuntimeError):
    """Generation-2 stop overlay violated a frozen research boundary."""


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
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _plain(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return hsse3._plain(value)


def _read_repo_bound(binding: Mapping[str, object], label: str) -> tuple[dict[str, object], bytes]:
    relative = binding.get("relative_path")
    expected = binding.get("git_blob_sha")
    if not isinstance(relative, str) or not isinstance(expected, str) or len(expected) != 40:
        raise Gen2StopError(f"{label} binding is invalid")
    target = (REPO_ROOT / relative).resolve()
    if not target.is_relative_to(REPO_ROOT.resolve()) or target.is_symlink():
        raise Gen2StopError(f"{label} path is unsafe")
    try:
        payload = target.read_bytes()
    except OSError:
        raise Gen2StopError(f"cannot read {label}") from None
    if not payload or len(payload) > MAX_BOUND_BYTES:
        raise Gen2StopError(f"{label} size is invalid")
    if _git_blob_sha(payload) != expected:
        raise Gen2StopError(f"{label} Git blob binding mismatch")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise Gen2StopError(f"{label} is not UTF-8 JSON") from None
    if not isinstance(record, dict):
        raise Gen2StopError(f"{label} must be an object")
    return record, payload


def validate_protocol(path: Path = DEFAULT_PROTOCOL_PATH) -> tuple[dict[str, object], str, dict[str, object], dict[str, object]]:
    target = path.resolve()
    if not target.is_relative_to(REPO_ROOT.resolve()) or target.is_symlink():
        raise Gen2StopError("protocol path is unsafe")
    try:
        payload = target.read_bytes()
    except OSError:
        raise Gen2StopError("cannot read GEN2-001 protocol") from None
    if not payload or len(payload) > MAX_PROTOCOL_BYTES:
        raise Gen2StopError("GEN2-001 protocol size is invalid")
    try:
        p = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise Gen2StopError("GEN2-001 protocol is not UTF-8 JSON") from None
    if (
        not isinstance(p, dict)
        or p.get("schema") != "YATL_GEN2_STOP_OVERLAY_PROTOCOL"
        or p.get("schema_version") != SCHEMA_VERSION
        or p.get("protocol_id") != "GEN2-001-STOP-OVERLAY-001"
        or p.get("status") != "REGISTERED_BEFORE_GEN2_STOP_OVERLAY_OUTCOMES"
        or p.get("source_candidate_id") != "RIE-CAND-0030"
        or p.get("research_only") is not True
        or p.get("p10_read") is not False
        or p.get("p10_write_allowed") is not False
        or p.get("p11_locked") is not True
        or p.get("no_rerank_after_outcomes") is not True
        or p.get("no_retune_after_outcomes") is not True
    ):
        raise Gen2StopError("GEN2-001 protocol identity/safety is invalid")

    matrix = p.get("trial_matrix")
    scope = p.get("development_scope")
    execution = p.get("execution")
    gate = p.get("proposal_gate")
    refs = p.get("reference_strategies")
    bindings = p.get("bindings")
    if not all(isinstance(x, dict) for x in (matrix, scope, execution, gate, refs, bindings)):
        raise Gen2StopError("GEN2-001 protocol scope is incomplete")
    if (
        matrix.get("stop_thresholds_percent") != [10, 20, 30, 40, 50]
        or matrix.get("reference_strategy_count") != 6
        or matrix.get("conditions_per_strategy") != 6
        or matrix.get("total_conditions") != 36
        or matrix.get("hidden_trials_forbidden") is not True
        or matrix.get("failed_trials_retained") is not True
    ):
        raise Gen2StopError("GEN2-001 trial matrix is invalid")
    if (
        scope.get("corpus_id") != "CRL-CONTROL-DEV-POOL-001"
        or scope.get("analysis_start_utc") != "2020-01-01T00:00:00Z"
        or scope.get("analysis_end_exclusive_utc") != "2023-01-01T00:00:00Z"
        or scope.get("selection_only") is not True
        or scope.get("hsse_004b_2023_2024_read_allowed") is not False
        or scope.get("hsse_005_outcomes_used_for_selection") is not False
        or scope.get("fresh_oos_read_allowed") is not False
        or scope.get("recent_reserve_read_allowed") is not False
    ):
        raise Gen2StopError("GEN2-001 Development boundary is invalid")
    if (
        execution.get("timeframe") != "1h"
        or execution.get("mode") != "LONG_ONLY_SPOT_RESEARCH"
        or execution.get("quantity") != "0.001"
        or execution.get("initial_equity_quote") != "10000"
        or execution.get("base_fee_bps") != 10
        or execution.get("base_adverse_slippage_bps") != 5
        or execution.get("stress_fee_bps") != 20
        or execution.get("stress_adverse_slippage_bps") != 10
    ):
        raise Gen2StopError("GEN2-001 execution policy is invalid")
    if (
        gate.get("minimum_reference_strategies_with_stop_fill") != 2
        or gate.get("minimum_total_stop_fills") != 6
        or gate.get("aggregate_base_net_must_exceed_control") is not True
        or gate.get("aggregate_stress_net_must_exceed_control") is not True
        or gate.get("median_reference_strategy_base_net_delta_must_be_positive") is not True
        or gate.get("median_reference_strategy_stress_net_delta_must_be_positive") is not True
        or gate.get("median_reference_strategy_drawdown_delta_must_be_negative") is not True
        or gate.get("at_least_reference_strategies_with_nonworse_drawdown") != 4
        or gate.get("zero_proposals_is_valid") is not True
    ):
        raise Gen2StopError("GEN2-001 proposal gate is invalid")

    extraction, _ = _read_repo_bound(bindings["method_extraction"], "RIE-CAND-0030 method extraction")
    freeze, _ = _read_repo_bound(bindings["survivor_freeze"], "HSSE-004A freeze")
    hsse_protocol, _ = _read_repo_bound(bindings["hsse_search_protocol"], "HSSE-001 protocol")
    if (
        extraction.get("candidate_id") != "RIE-CAND-0030"
        or extraction.get("status") != "METHOD_READY_PROTOCOL_NOT_FROZEN"
        or extraction.get("performance_run_allowed") is not False
    ):
        raise Gen2StopError("method extraction identity is invalid")
    survivors = freeze.get("survivors")
    expected_ids = refs.get("frozen_ids")
    if (
        freeze.get("freeze_id") != "HSSE-004A-SURVIVOR-FREEZE-001"
        or not isinstance(survivors, list)
        or len(survivors) != 6
        or [x.get("frozen_id") for x in survivors] != expected_ids
    ):
        raise Gen2StopError("HSSE-004A survivor binding is invalid")
    folds = hsse_protocol.get("development_cross_validation", {}).get("folds")
    if (
        hsse_protocol.get("protocol_id") != "HSSE-001-SEARCH-PROTOCOL"
        or not isinstance(folds, list)
        or len(folds) != 5
        or folds[0].get("evaluation_start_utc") != "2020-07-01T00:00:00Z"
        or folds[-1].get("evaluation_end_exclusive_utc") != "2023-01-01T00:00:00Z"
    ):
        raise Gen2StopError("HSSE Development fold binding is invalid")
    return p, _sha256(payload), freeze, hsse_protocol


def _series(corpus: controls.AdmittedControlCorpus, symbol: str):
    candles = corpus.datasets[(symbol, "1h")]
    times = tuple(x.open_time_ms for x in candles)
    if (
        not candles
        or times != tuple(sorted(times))
        or len(times) != len(set(times))
        or any(not x.is_closed for x in candles)
    ):
        raise Gen2StopError(f"invalid Development 1h series for {symbol}")
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


def _simulate_cell(
    *,
    signal: hsse2.SearchSeries,
    exact: hsse3.ExactSeries,
    short_values,
    long_values,
    start_ms: int,
    end_ms: int,
    threshold_percent: int | None,
    policy: Mapping[str, object],
) -> dict[str, object]:
    if signal.times != exact.times:
        raise Gen2StopError("signal/exact timestamps differ")
    start = bisect.bisect_left(exact.times, start_ms)
    end = bisect.bisect_left(exact.times, end_ms)
    if start >= end:
        raise Gen2StopError("Development cell is empty")
    if threshold_percent is not None and threshold_percent not in (10, 20, 30, 40, 50):
        raise Gen2StopError("stop threshold is outside frozen grid")

    quantity = Decimal(str(policy["quantity"]))
    initial = Decimal(str(policy["initial_equity_quote"]))
    bf = Decimal(str(policy["base_fee_bps"]))
    bs = Decimal(str(policy["base_adverse_slippage_bps"]))
    sf = Decimal(str(policy["stress_fee_bps"]))
    ss = Decimal(str(policy["stress_adverse_slippage_bps"]))
    base = hsse3._new_account(initial)
    stress = hsse3._new_account(initial)

    position = False
    entry_reference: Decimal | None = None
    peak = initial
    maxdd = Decimal(0)
    entries = ordinary_exits = stop_exits = dual_exits = 0
    missing_signal_fills = missing_stop_fills = 0

    for i in range(start, end):
        close = Decimal(exact.closes[i])
        equity = hsse3._equity(
            base,
            mark=close,
            quantity=quantity,
            fee_bps=bf,
            slippage_bps=bs,
        )
        with localcontext() as ctx:
            ctx.prec = hsse3.DECIMAL_PRECISION
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
        if dd > maxdd:
            maxdd = dd
        if i == 0:
            continue

        vals = (short_values[i], long_values[i], short_values[i - 1], long_values[i - 1])
        if not all(math.isfinite(v) for v in vals):
            continue
        sn, ln, sp, lp = vals
        ordinary_exit = position and sn < ln and sp >= lp
        stop_exit = False
        if position and threshold_percent is not None:
            if entry_reference is None:
                raise Gen2StopError("open position is missing entry reference")
            with localcontext() as ctx:
                ctx.prec = hsse3.DECIMAL_PRECISION
                stop_level = entry_reference * (
                    Decimal(1) - Decimal(threshold_percent) / Decimal(100)
                )
            stop_exit = close <= stop_level

        if position and (ordinary_exit or stop_exit):
            fi = i + 1
            if fi >= end or fi >= len(exact.times) or exact.times[fi] != exact.times[i] + HOUR_MS:
                if stop_exit:
                    missing_stop_fills += 1
                else:
                    missing_signal_fills += 1
                continue
            reference = Decimal(exact.opens[fi])
            hsse3._exit(base, reference=reference, quantity=quantity, fee_bps=bf, slippage_bps=bs)
            hsse3._exit(stress, reference=reference, quantity=quantity, fee_bps=sf, slippage_bps=ss)
            position = False
            entry_reference = None
            if ordinary_exit and stop_exit:
                dual_exits += 1
            elif stop_exit:
                stop_exits += 1
            else:
                ordinary_exits += 1
            continue

        enter = (not position) and sn > ln and sp <= lp
        if not enter:
            continue
        fi = i + 1
        if fi >= end or fi >= len(exact.times) or exact.times[fi] != exact.times[i] + HOUR_MS:
            missing_signal_fills += 1
            continue
        reference = Decimal(exact.opens[fi])
        hsse3._entry(base, reference=reference, quantity=quantity, fee_bps=bf, slippage_bps=bs)
        hsse3._entry(stress, reference=reference, quantity=quantity, fee_bps=sf, slippage_bps=ss)
        position = True
        entry_reference = reference
        entries += 1

    final_mark = Decimal(exact.closes[end - 1])
    base_final = hsse3._equity(
        base, mark=final_mark, quantity=quantity, fee_bps=bf, slippage_bps=bs
    )
    stress_final = hsse3._equity(
        stress, mark=final_mark, quantity=quantity, fee_bps=sf, slippage_bps=ss
    )
    with localcontext() as ctx:
        ctx.prec = hsse3.DECIMAL_PRECISION
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
        ctx.prec = hsse3.DECIMAL_PRECISION
        expectancy = realized / Decimal(completed) if completed else Decimal(0)
    return {
        "base_net": base_net,
        "stress_net": stress_net,
        "realized": realized,
        "stress_realized": stress_realized,
        "maximum_drawdown": maxdd,
        "completed_trades": completed,
        "expectancy": expectancy,
        "profit_factor": pf_text,
        "profit_factor_infinite": pf_inf,
        "entry_fills": entries,
        "ordinary_exit_fills": ordinary_exits,
        "stop_exit_fills": stop_exits,
        "dual_exit_fills": dual_exits,
        "missing_signal_fills": missing_signal_fills,
        "missing_stop_fills": missing_stop_fills,
        "open_position_at_end": position,
    }


def _aggregate_condition(
    *,
    survivor: Mapping[str, object],
    threshold_percent: int | None,
    folds: Sequence[Mapping[str, object]],
    signal_series: Mapping[str, hsse2.SearchSeries],
    exact_series: Mapping[str, hsse3.ExactSeries],
    cache: dict[tuple[str, str, int], object],
    policy: Mapping[str, object],
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
    completed = stop_fills = 0
    for fold in folds:
        start_ms = hsse3._time_ms(fold["evaluation_start_utc"], "fold start")
        end_ms = hsse3._time_ms(fold["evaluation_end_exclusive_utc"], "fold end")
        for symbol in sorted(signal_series):
            c = _simulate_cell(
                signal=signal_series[symbol],
                exact=exact_series[symbol],
                short_values=cache[(symbol, family, n1)],
                long_values=cache[(symbol, family, n2)],
                start_ms=start_ms,
                end_ms=end_ms,
                threshold_percent=threshold_percent,
                policy=policy,
            )
            nets.append(c["base_net"])
            stress_nets.append(c["stress_net"])
            realized.append(c["realized"])
            stress_realized.append(c["stress_realized"])
            maxdd = max(maxdd, c["maximum_drawdown"])
            completed += int(c["completed_trades"])
            stop_fills += int(c["stop_exit_fills"]) + int(c["dual_exit_fills"])
            cells.append({
                "fold_id": fold["fold_id"],
                "symbol": symbol,
                "base_net_pnl_after_costs_quote": _plain(c["base_net"]),
                "stress_net_pnl_after_costs_quote": _plain(c["stress_net"]),
                "maximum_drawdown_fraction": _plain(c["maximum_drawdown"]),
                "completed_trades": c["completed_trades"],
                "stop_exit_fills": c["stop_exit_fills"],
                "dual_exit_fills": c["dual_exit_fills"],
                "missing_stop_fills": c["missing_stop_fills"],
            })
    total_net = hsse3._sum(nets)
    total_stress = hsse3._sum(stress_nets)
    total_realized = hsse3._sum(realized)
    total_stress_realized = hsse3._sum(stress_realized)
    with localcontext() as ctx:
        ctx.prec = hsse3.DECIMAL_PRECISION
        expectancy = total_realized / Decimal(completed) if completed else Decimal(0)
        stress_expectancy = (
            total_stress_realized / Decimal(completed) if completed else Decimal(0)
        )
    return {
        "frozen_id": survivor["frozen_id"],
        "family": family,
        "parameters": survivor["parameters"],
        "threshold_percent": threshold_percent,
        "base_total_net_pnl_after_costs_quote": _plain(total_net),
        "stress_total_net_pnl_after_costs_quote": _plain(total_stress),
        "base_expectancy_quote": _plain(expectancy),
        "stress_expectancy_quote": _plain(stress_expectancy),
        "maximum_drawdown_fraction": _plain(maxdd),
        "completed_trades": completed,
        "total_stop_fills": stop_fills,
        "cells": cells,
    }


def _write_result(root: Path, record: Mapping[str, object]) -> tuple[str, str]:
    payload = _canonical_json(record)
    digest = _sha256(payload)
    safe = root.resolve()
    out = safe / "generation-2" / "gen2-001"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"stop-overlay-{digest[:24]}.json"
    if path.exists():
        if path.read_bytes() != payload:
            raise Gen2StopError("existing GEN2-001 artifact differs")
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as h:
            h.write(payload)
            h.flush()
            os.fsync(h.fileno())
    return path.relative_to(safe).as_posix(), digest


def run(*, runtime_root: Path, protocol_path: Path = DEFAULT_PROTOCOL_PATH) -> dict[str, object]:
    protocol, protocol_sha, freeze, hsse_protocol = validate_protocol(protocol_path)
    q = protocol["bindings"]["development_quality_manifest"]
    try:
        corpus = controls._load_control_corpus(
            runtime_root=runtime_root,
            quality_manifest_relative_path=q["relative_path"],
            quality_manifest_file_sha256=q["file_sha256"],
        )
    except controls.ControlError as exc:
        raise Gen2StopError(str(exc)) from None

    signal_series = {}
    exact_series = {}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        signal_series[symbol], exact_series[symbol] = _series(corpus, symbol)
    folds = hsse_protocol["development_cross_validation"]["folds"]
    policy = protocol["execution"]
    cache: dict[tuple[str, str, int], object] = {}

    survivors = freeze["survivors"]
    controls_by_id = {}
    for s in survivors:
        controls_by_id[s["frozen_id"]] = _aggregate_condition(
            survivor=s,
            threshold_percent=None,
            folds=folds,
            signal_series=signal_series,
            exact_series=exact_series,
            cache=cache,
            policy=policy,
        )

    threshold_results = []
    proposals = []
    for threshold in protocol["trial_matrix"]["stop_thresholds_percent"]:
        rows = []
        base_deltas = []
        stress_deltas = []
        dd_deltas = []
        aggregate_overlay_base = Decimal(0)
        aggregate_control_base = Decimal(0)
        aggregate_overlay_stress = Decimal(0)
        aggregate_control_stress = Decimal(0)
        activated_refs = total_stop_fills = nonworse_dd = 0

        for s in survivors:
            row = _aggregate_condition(
                survivor=s,
                threshold_percent=int(threshold),
                folds=folds,
                signal_series=signal_series,
                exact_series=exact_series,
                cache=cache,
                policy=policy,
            )
            control = controls_by_id[s["frozen_id"]]
            onet = Decimal(row["base_total_net_pnl_after_costs_quote"])
            cnet = Decimal(control["base_total_net_pnl_after_costs_quote"])
            osnet = Decimal(row["stress_total_net_pnl_after_costs_quote"])
            csnet = Decimal(control["stress_total_net_pnl_after_costs_quote"])
            odd = Decimal(row["maximum_drawdown_fraction"])
            cdd = Decimal(control["maximum_drawdown_fraction"])
            base_deltas.append(onet - cnet)
            stress_deltas.append(osnet - csnet)
            dd_deltas.append(odd - cdd)
            aggregate_overlay_base += onet
            aggregate_control_base += cnet
            aggregate_overlay_stress += osnet
            aggregate_control_stress += csnet
            fills = int(row["total_stop_fills"])
            total_stop_fills += fills
            if fills > 0:
                activated_refs += 1
            if odd <= cdd:
                nonworse_dd += 1
            rows.append(row)

        median_base = hsse3._median_decimal(base_deltas)
        median_stress = hsse3._median_decimal(stress_deltas)
        median_dd = hsse3._median_decimal(dd_deltas)
        gate_reasons = []
        g = protocol["proposal_gate"]
        if activated_refs < int(g["minimum_reference_strategies_with_stop_fill"]):
            gate_reasons.append("STOP_ACTIVATION_REFERENCE_COUNT")
        if total_stop_fills < int(g["minimum_total_stop_fills"]):
            gate_reasons.append("STOP_ACTIVATION_FILL_COUNT")
        if aggregate_overlay_base <= aggregate_control_base:
            gate_reasons.append("AGGREGATE_BASE_NET_NOT_IMPROVED")
        if aggregate_overlay_stress <= aggregate_control_stress:
            gate_reasons.append("AGGREGATE_STRESS_NET_NOT_IMPROVED")
        if median_base <= 0:
            gate_reasons.append("MEDIAN_BASE_NET_DELTA_NOT_POSITIVE")
        if median_stress <= 0:
            gate_reasons.append("MEDIAN_STRESS_NET_DELTA_NOT_POSITIVE")
        if median_dd >= 0:
            gate_reasons.append("MEDIAN_DRAWDOWN_DELTA_NOT_NEGATIVE")
        if nonworse_dd < int(g["at_least_reference_strategies_with_nonworse_drawdown"]):
            gate_reasons.append("NONWORSE_DRAWDOWN_REFERENCE_COUNT")
        status = "PASS" if not gate_reasons else "FAIL"
        if status == "PASS":
            proposals.append(int(threshold))
        threshold_results.append({
            "threshold_percent": int(threshold),
            "status": status,
            "failure_reasons": gate_reasons,
            "activated_reference_strategies": activated_refs,
            "total_stop_fills": total_stop_fills,
            "reference_strategies_with_nonworse_drawdown": nonworse_dd,
            "aggregate_overlay_base_net_quote": _plain(aggregate_overlay_base),
            "aggregate_control_base_net_quote": _plain(aggregate_control_base),
            "aggregate_overlay_stress_net_quote": _plain(aggregate_overlay_stress),
            "aggregate_control_stress_net_quote": _plain(aggregate_control_stress),
            "median_base_net_delta_quote": _plain(median_base),
            "median_stress_net_delta_quote": _plain(median_stress),
            "median_drawdown_delta_fraction": _plain(median_dd),
            "conditions": rows,
        })

    record = {
        "schema": "YATL_GEN2_STOP_OVERLAY_RESULT",
        "schema_version": SCHEMA_VERSION,
        "implementation_id": IMPLEMENTATION_ID,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha,
        "source_candidate_id": "RIE-CAND-0030",
        "development_corpus_id": "CRL-CONTROL-DEV-POOL-001",
        "condition_count": 36,
        "proposal_thresholds_percent": proposals,
        "proposal_count": len(proposals),
        "control_conditions": [controls_by_id[s["frozen_id"]] for s in survivors],
        "threshold_results": threshold_results,
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
    summary = {
        "implementation_id": IMPLEMENTATION_ID,
        "protocol_sha256": protocol_sha,
        "condition_count": 36,
        "proposal_count": len(proposals),
        "proposal_thresholds_percent": proposals,
        "artifact_relative_path": artifact_rel,
        "artifact_file_sha256": artifact_sha,
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
    }
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)
    parser.add_argument("--validate-protocol-only", action="store_true")
    args = parser.parse_args(argv)
    if args.validate_protocol_only:
        protocol, sha, freeze, hsse = validate_protocol(args.protocol)
        print(_json({
            "implementation_id": IMPLEMENTATION_ID,
            "protocol_id": protocol["protocol_id"],
            "protocol_sha256": sha,
            "survivor_count": len(freeze["survivors"]),
            "fold_count": len(hsse["development_cross_validation"]["folds"]),
            "condition_count": protocol["trial_matrix"]["total_conditions"],
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
