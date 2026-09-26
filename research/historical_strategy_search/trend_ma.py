"""HSSE-002 deterministic Development-only moving-average search.

This high-throughput discovery runner evaluates the preregistered SMA/EMA/DEMA
parameter grid only on the already-exposed CRL Development corpus. It never
reads HSSE Blind OOS or final-audit datasets. Search arithmetic is binary64 by
protocol; every proposed survivor requires independent exact recomputation in
HSSE-003 before any survivor freeze.
"""

from __future__ import annotations

import argparse
import bisect
import gc
import hashlib
import json
import math
import os
import sys
import tempfile
from array import array
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Mapping, Sequence

from yatl.data import INTERVAL_MILLISECONDS

from research.crisis_lab import controls, replay
from research.research_intake import registry as rie
from research.research_intake import reproduction as rp

from . import protocol as hsse1


IMPLEMENTATION_ID = "HSSE-002-TREND-MA-SEARCH/0.1.0"
SCHEMA_VERSION = "0.1.0"
DEFAULT_PLAN_PATH = Path(
    "docs/research/historical-strategy-search/"
    "HSSE-002-TREND-MA-SEARCH-PLAN-v0.1.0.json"
)
MAX_PLAN_BYTES = 1024 * 1024
HOUR_MS = INTERVAL_MILLISECONDS["1h"]
FAMILIES = ("TREND_MA_SMA", "TREND_MA_EMA", "TREND_MA_DEMA")


class HSSESearchError(RuntimeError):
    """HSSE-002 violated a frozen search or data boundary."""


@dataclass(frozen=True, slots=True)
class SearchSeries:
    symbol: str
    times: tuple[int, ...]
    opens: tuple[float, ...]
    closes: tuple[float, ...]


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
    header = b"blob " + str(len(payload)).encode("ascii") + b"\0"
    return hashlib.sha1(header + payload).hexdigest()


def _num(value: float) -> str:
    if not math.isfinite(value):
        raise HSSESearchError("HSSE-002 arithmetic is not finite")
    if abs(value) < 5e-16:
        return "0"
    return format(value, ".17g")


def _read_json(path: Path, maximum: int, label: str) -> tuple[dict[str, object], bytes]:
    if path.is_symlink():
        raise HSSESearchError(f"symlink {label} is forbidden")
    try:
        payload = path.read_bytes()
    except OSError:
        raise HSSESearchError(f"cannot read {label}") from None
    if not payload or len(payload) > maximum:
        raise HSSESearchError(f"{label} size is invalid")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HSSESearchError(f"{label} is not UTF-8 JSON") from None
    if not isinstance(record, dict):
        raise HSSESearchError(f"{label} must be an object")
    return record, payload


def _bound_path(
    plan_path: Path,
    relative: object,
    expected_blob_sha: object,
    label: str,
) -> Path:
    if (
        not isinstance(relative, str)
        or not relative
        or not isinstance(expected_blob_sha, str)
        or len(expected_blob_sha) != 40
    ):
        raise HSSESearchError(f"{label} binding is invalid")
    resolved_plan = plan_path.resolve()
    try:
        repo_root = resolved_plan.parents[3]
    except IndexError:
        raise HSSESearchError("HSSE plan is not inside the repository") from None
    target = (repo_root / relative).resolve()
    if not target.is_relative_to(repo_root):
        raise HSSESearchError(f"{label} escapes repository root")
    try:
        payload = target.read_bytes()
    except OSError:
        raise HSSESearchError(f"cannot read bound {label}") from None
    if _git_blob_sha(payload) != expected_blob_sha:
        raise HSSESearchError(f"{label} Git blob binding mismatch")
    return target


def load_plan(
    path: Path = DEFAULT_PLAN_PATH,
) -> tuple[dict[str, object], str, dict[str, object]]:
    record, payload = _read_json(path, MAX_PLAN_BYTES, "HSSE-002 plan")
    if (
        record.get("schema") != "YATL_HSSE_SEARCH_PLAN"
        or record.get("schema_version") != SCHEMA_VERSION
        or record.get("plan_id") != "HSSE-002-TREND-MA-SEARCH-001"
        or record.get("status") != "REGISTERED_BEFORE_HSSE002_SEARCH_OUTCOMES"
        or record.get("candidate_id") != "RIE-CAND-0020"
        or record.get("research_only") is not True
        or record.get("p10_read") is not False
        or record.get("p10_write_allowed") is not False
        or record.get("p10_evidence_effect") != "NONE"
        or record.get("trade_permission") is not False
        or record.get("order_endpoint") is not False
        or record.get("quantity_authority") is not False
        or record.get("risk_authorization_mutation") is not False
        or record.get("ai_direct_execution") is not False
        or record.get("p11_locked") is not True
    ):
        raise HSSESearchError("HSSE-002 plan safety invariants are invalid")

    bindings = record.get("bindings")
    if not isinstance(bindings, dict):
        raise HSSESearchError("HSSE-002 bindings are missing")
    protocol_path = _bound_path(
        path,
        bindings.get("hsse_protocol_relative_path"),
        bindings.get("hsse_protocol_git_blob_sha"),
        "HSSE-001 protocol",
    )
    registry_path = _bound_path(
        path,
        bindings.get("registry_relative_path"),
        bindings.get("registry_git_blob_sha"),
        "RIE registry",
    )
    packet_path = _bound_path(
        path,
        bindings.get("reproduction_packet_relative_path"),
        bindings.get("reproduction_packet_git_blob_sha"),
        "RIE reproduction packet",
    )

    try:
        protocol_result = hsse1.validate_protocol(protocol_path)
        registry_result = rie.validate_registry(registry_path)
        packet_result = rp.validate_packet(packet_path)
    except (hsse1.HSSEProtocolError, rie.ResearchIntakeError, rp.ReproductionPacketError) as exc:
        raise HSSESearchError(str(exc)) from None

    registry_record, _ = _read_json(
        registry_path, rie.MAX_REGISTRY_BYTES, "RIE registry"
    )
    candidates = registry_record.get("candidates")
    candidate = next(
        (
            item
            for item in candidates
            if isinstance(item, dict)
            and item.get("candidate_id") == record["candidate_id"]
        ),
        None,
    )
    if not isinstance(candidate, dict):
        raise HSSESearchError("bound search candidate is missing")
    if (
        candidate.get("status") != "READY_FOR_TRAIN_SEARCH"
        or rie.candidate_fingerprint(candidate)
        != record.get("candidate_fingerprint_sha256")
        or packet_result["candidate_id"] != record["candidate_id"]
        or packet_result["ready_for_train_search"] is not True
        or registry_result["reproduction_packet_count"] < 1
    ):
        raise HSSESearchError("search candidate is not frozen and eligible")

    matrix = record.get("trial_matrix")
    windows = matrix.get("window_values") if isinstance(matrix, dict) else None
    if (
        not isinstance(matrix, dict)
        or matrix.get("family_order") != list(FAMILIES)
        or not isinstance(windows, dict)
        or windows.get("start") != 1
        or windows.get("stop_exclusive") != 1000
        or windows.get("step") != 10
        or windows.get("count") != 100
        or matrix.get("pair_constraint") != "n1<n2"
        or matrix.get("trials_per_family") != 4950
        or matrix.get("total_trials") != 14850
        or matrix.get("hidden_trials_forbidden") is not True
        or matrix.get("failed_trials_retained") is not True
    ):
        raise HSSESearchError("HSSE-002 trial matrix is invalid")
    generated = tuple(range(1, 1000, 10))
    if len(generated) != 100 or len(_trial_pairs(generated)) != 4950:
        raise HSSESearchError("HSSE-002 generated grid differs from registration")

    execution = record.get("execution_semantics")
    data_scope = record.get("data_scope")
    signal = record.get("signal_semantics")
    numeric = record.get("numeric_policy")
    artifact = record.get("artifact_policy")
    protocol, _ = _read_json(protocol_path, hsse1.MAX_PROTOCOL_BYTES, "HSSE-001 protocol")
    pexec = protocol["execution_semantics"]
    pdev = protocol["data_boundaries"]["development"]
    if (
        not isinstance(execution, dict)
        or execution.get("quantity") != "0.001"
        or execution.get("initial_equity_quote") != "10000"
        or execution.get("base_fee_bps") != pexec["fee_bps"]
        or execution.get("base_adverse_slippage_bps") != pexec["adverse_slippage_bps"]
        or execution.get("stress_fee_bps") != pexec["cost_stress"]["fee_bps"]
        or execution.get("stress_adverse_slippage_bps")
        != pexec["cost_stress"]["adverse_slippage_bps"]
        or execution.get("mode") != "LONG_ONLY_SPOT_RESEARCH"
        or execution.get("next_open") is not True
        or execution.get("shorting") is not False
        or execution.get("futures") is not False
        or execution.get("leverage") is not False
        or not isinstance(data_scope, dict)
        or data_scope.get("corpus_id") != pdev["corpus_id"]
        or data_scope.get("warmup_start_utc") != pdev["warmup_start_utc"]
        or data_scope.get("development_only") is not True
        or data_scope.get("blind_oos_read_allowed") is not False
        or data_scope.get("audit_holdout_read_allowed") is not False
        or not isinstance(signal, dict)
        or signal.get("timeframe") != "1h"
        or not isinstance(numeric, dict)
        or numeric.get("search_signal_math") != "PYTHON_BINARY64"
        or numeric.get("search_economics_math") != "PYTHON_BINARY64"
        or numeric.get("exact_recompute_required_before_survivor_freeze") is not True
        or not isinstance(artifact, dict)
        or artifact.get("every_trial_recorded") is not True
        or artifact.get("content_addressed_immutable") is not True
        or artifact.get("top_performer_printed_to_cli") is not False
    ):
        raise HSSESearchError("HSSE-002 execution/data/numeric contract is invalid")

    context = {
        "protocol_path": protocol_path,
        "registry_path": registry_path,
        "packet_path": packet_path,
        "protocol": protocol,
        "candidate": candidate,
        "packet_result": packet_result,
        "protocol_result": protocol_result,
    }
    return record, _sha256(payload), context


def _trial_pairs(windows: Sequence[int]) -> list[tuple[int, int]]:
    return [
        (short, long)
        for short in windows
        for long in windows
        if short < long
    ]


def _series_for_symbol(corpus: controls.AdmittedControlCorpus, symbol: str) -> SearchSeries:
    candles = corpus.datasets.get((symbol, "1h"))
    if not candles:
        raise HSSESearchError(f"missing 1h Development data for {symbol}")
    times = tuple(item.open_time_ms for item in candles)
    if (
        len(times) != len(set(times))
        or times != tuple(sorted(times))
        or any(not item.is_closed for item in candles)
    ):
        raise HSSESearchError(f"invalid 1h Development series for {symbol}")
    return SearchSeries(
        symbol=symbol,
        times=times,
        opens=tuple(float(item.open) for item in candles),
        closes=tuple(float(item.close) for item in candles),
    )


def _indicator_series(
    series: SearchSeries,
    family: str,
    window: int,
) -> array:
    if family not in FAMILIES or type(window) is not int or window < 1:
        raise HSSESearchError("indicator request is invalid")
    n = len(series.closes)
    out = array("d", [math.nan]) * n
    closes = series.closes
    times = series.times

    if family == "TREND_MA_SMA":
        rolling = 0.0
        segment_start = 0
        for i, price in enumerate(closes):
            if i == 0 or times[i] != times[i - 1] + HOUR_MS:
                segment_start = i
                rolling = price
            else:
                rolling += price
            run = i - segment_start + 1
            if run > window:
                rolling -= closes[i - window]
            if run >= window:
                out[i] = rolling / window
        return out

    alpha = 2.0 / (window + 1.0)
    ema1 = 0.0
    ema2 = 0.0
    run = 0
    for i, price in enumerate(closes):
        if i == 0 or times[i] != times[i - 1] + HOUR_MS:
            ema1 = price
            ema2 = price
            run = 1
        else:
            ema1 = alpha * price + (1.0 - alpha) * ema1
            ema2 = alpha * ema1 + (1.0 - alpha) * ema2
            run += 1
        if run >= window:
            out[i] = ema1 if family == "TREND_MA_EMA" else 2.0 * ema1 - ema2
    return out


def _indicator_grid(
    series: SearchSeries,
    family: str,
    windows: Sequence[int],
) -> dict[int, array]:
    return {
        window: _indicator_series(series, family, window)
        for window in windows
    }


def _cell(
    *,
    series: SearchSeries,
    short_values: array,
    long_values: array,
    start_ms: int,
    end_ms: int,
    quantity: float,
    initial: float,
    base_fee: float,
    base_slippage: float,
    stress_fee: float,
    stress_slippage: float,
) -> dict[str, object]:
    times = series.times
    opens = series.opens
    closes = series.closes
    start = bisect.bisect_left(times, start_ms)
    end = bisect.bisect_left(times, end_ms)
    if start >= end:
        raise HSSESearchError("Development cell has no primary candles")

    base_cash = initial
    stress_cash = initial
    position = False
    base_entry_debit = 0.0
    stress_entry_debit = 0.0
    completed = wins = losses = breakeven = 0
    base_realized = 0.0
    stress_realized = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    largest_positive = 0.0
    base_cost = 0.0
    missing_fill = 0
    entry_fills = 0
    exit_fills = 0
    peak = initial
    max_drawdown = 0.0

    for i in range(start, end):
        close = closes[i]
        equity = base_cash + (quantity * close if position else 0.0)
        if equity > peak:
            peak = equity
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)

        if i == 0:
            continue
        sv = short_values[i]
        lv = long_values[i]
        ps = short_values[i - 1]
        pl = long_values[i - 1]
        if not all(math.isfinite(v) for v in (sv, lv, ps, pl)):
            continue

        enter = (not position) and sv > lv and ps <= pl
        exit_ = position and sv < lv and ps >= pl
        if not enter and not exit_:
            continue
        fill_i = i + 1
        if (
            fill_i >= end
            or fill_i >= len(times)
            or times[fill_i] != times[i] + HOUR_MS
        ):
            missing_fill += 1
            continue

        reference = opens[fill_i]
        if enter:
            base_exec = reference * (1.0 + base_slippage)
            stress_exec = reference * (1.0 + stress_slippage)
            base_fee_quote = quantity * base_exec * base_fee
            stress_fee_quote = quantity * stress_exec * stress_fee
            base_entry_debit = quantity * base_exec + base_fee_quote
            stress_entry_debit = quantity * stress_exec + stress_fee_quote
            if base_entry_debit > base_cash or stress_entry_debit > stress_cash:
                raise HSSESearchError("fixed research quantity exceeds cell equity")
            base_cash -= base_entry_debit
            stress_cash -= stress_entry_debit
            base_cost += quantity * (base_exec - reference) + base_fee_quote
            position = True
            entry_fills += 1
            continue

        base_exec = reference * (1.0 - base_slippage)
        stress_exec = reference * (1.0 - stress_slippage)
        base_fee_quote = quantity * base_exec * base_fee
        stress_fee_quote = quantity * stress_exec * stress_fee
        base_proceeds = quantity * base_exec - base_fee_quote
        stress_proceeds = quantity * stress_exec - stress_fee_quote
        base_cash += base_proceeds
        stress_cash += stress_proceeds
        base_pnl = base_proceeds - base_entry_debit
        stress_pnl = stress_proceeds - stress_entry_debit
        base_realized += base_pnl
        stress_realized += stress_pnl
        completed += 1
        if base_pnl > 0:
            wins += 1
            gross_profit += base_pnl
            largest_positive = max(largest_positive, base_pnl)
        elif base_pnl < 0:
            losses += 1
            gross_loss += -base_pnl
        else:
            breakeven += 1
        base_cost += quantity * (reference - base_exec) + base_fee_quote
        position = False
        exit_fills += 1

    last_close = closes[end - 1]
    base_final = base_cash + (quantity * last_close if position else 0.0)
    stress_final = stress_cash + (quantity * last_close if position else 0.0)
    base_net = base_final - initial
    stress_net = stress_final - initial
    return {
        "completed_trades": completed,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "entry_fills": entry_fills,
        "exit_fills": exit_fills,
        "missing_fill_signals": missing_fill,
        "open_position_at_end": position,
        "base": {
            "net_pnl_after_costs_quote": base_net,
            "net_return_after_costs": base_net / initial,
            "realized_closed_trade_pnl_quote": base_realized,
            "gross_profit_quote": gross_profit,
            "gross_loss_quote": gross_loss,
            "largest_positive_trade_quote": largest_positive,
            "executed_cost_quote": base_cost,
            "maximum_drawdown_fraction": max_drawdown,
        },
        "stress": {
            "net_pnl_after_costs_quote": stress_net,
            "net_return_after_costs": stress_net / initial,
            "realized_closed_trade_pnl_quote": stress_realized,
        },
    }


def _quartile_lower(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        raise HSSESearchError("cannot compute quartile for empty cells")
    lower = ordered[: len(ordered) // 2]
    return median(lower if lower else ordered)


def _profit_factor(gross_profit: float, gross_loss: float) -> tuple[str | None, bool]:
    if gross_loss == 0.0:
        return None, gross_profit > 0.0
    return _num(gross_profit / gross_loss), False


def _trial(
    *,
    family: str,
    n1: int,
    n2: int,
    series_by_symbol: Mapping[str, SearchSeries],
    indicators_by_symbol: Mapping[str, Mapping[int, array]],
    folds: Sequence[Mapping[str, object]],
    execution: Mapping[str, object],
    filters: Mapping[str, object],
) -> dict[str, object]:
    quantity = float(execution["quantity"])
    initial = float(execution["initial_equity_quote"])
    base_fee = float(execution["base_fee_bps"]) / 10000.0
    base_slip = float(execution["base_adverse_slippage_bps"]) / 10000.0
    stress_fee = float(execution["stress_fee_bps"]) / 10000.0
    stress_slip = float(execution["stress_adverse_slippage_bps"]) / 10000.0

    cells: list[dict[str, object]] = []
    total_completed = wins = losses = breakeven = 0
    total_base_net = total_stress_net = 0.0
    total_base_realized = total_stress_realized = 0.0
    gross_profit = gross_loss = largest_positive = 0.0
    maximum_drawdown = 0.0
    positive_cells = 0
    returns: list[float] = []
    per_symbol = {symbol: 0 for symbol in sorted(series_by_symbol)}

    for fold in folds:
        start_ms = int(
            __import__("datetime").datetime.fromisoformat(
                str(fold["evaluation_start_utc"]).replace("Z", "+00:00")
            ).timestamp()
            * 1000
        )
        end_ms = int(
            __import__("datetime").datetime.fromisoformat(
                str(fold["evaluation_end_exclusive_utc"]).replace("Z", "+00:00")
            ).timestamp()
            * 1000
        )
        for symbol in sorted(series_by_symbol):
            result = _cell(
                series=series_by_symbol[symbol],
                short_values=indicators_by_symbol[symbol][n1],
                long_values=indicators_by_symbol[symbol][n2],
                start_ms=start_ms,
                end_ms=end_ms,
                quantity=quantity,
                initial=initial,
                base_fee=base_fee,
                base_slippage=base_slip,
                stress_fee=stress_fee,
                stress_slippage=stress_slip,
            )
            base = result["base"]
            stress = result["stress"]
            completed = int(result["completed_trades"])
            total_completed += completed
            wins += int(result["wins"])
            losses += int(result["losses"])
            breakeven += int(result["breakeven"])
            per_symbol[symbol] += completed
            total_base_net += float(base["net_pnl_after_costs_quote"])
            total_stress_net += float(stress["net_pnl_after_costs_quote"])
            total_base_realized += float(base["realized_closed_trade_pnl_quote"])
            total_stress_realized += float(stress["realized_closed_trade_pnl_quote"])
            gross_profit += float(base["gross_profit_quote"])
            gross_loss += float(base["gross_loss_quote"])
            largest_positive = max(
                largest_positive, float(base["largest_positive_trade_quote"])
            )
            maximum_drawdown = max(
                maximum_drawdown, float(base["maximum_drawdown_fraction"])
            )
            cell_return = float(base["net_return_after_costs"])
            returns.append(cell_return)
            if float(base["net_pnl_after_costs_quote"]) > 0.0:
                positive_cells += 1
            cells.append(
                {
                    "fold_id": fold["fold_id"],
                    "symbol": symbol,
                    "completed_trades": completed,
                    "base_net_return_after_costs": _num(cell_return),
                    "stress_net_return_after_costs": _num(
                        float(stress["net_return_after_costs"])
                    ),
                    "maximum_drawdown_fraction": _num(
                        float(base["maximum_drawdown_fraction"])
                    ),
                }
            )

    pf, pf_infinite = _profit_factor(gross_profit, gross_loss)
    expectancy = (
        total_base_realized / total_completed if total_completed else 0.0
    )
    stress_expectancy = (
        total_stress_realized / total_completed if total_completed else 0.0
    )
    concentration = (
        largest_positive / gross_profit if gross_profit > 0.0 else 0.0
    )
    positive_fraction = positive_cells / len(cells)
    median_return = median(returns)
    lower_quartile = _quartile_lower(returns)

    reasons: list[str] = []
    if total_completed < int(filters["minimum_completed_trades_total"]):
        reasons.append("MINIMUM_COMPLETED_TRADES_TOTAL")
    if any(
        count < int(filters["minimum_completed_trades_per_symbol"])
        for count in per_symbol.values()
    ):
        reasons.append("MINIMUM_COMPLETED_TRADES_PER_SYMBOL")
    if total_base_net <= 0.0:
        reasons.append("TOTAL_NET_PNL_NOT_POSITIVE")
    if expectancy <= 0.0:
        reasons.append("EXPECTANCY_NOT_POSITIVE")
    minimum_pf = float(filters["minimum_profit_factor_after_base_costs"])
    if not pf_infinite and (pf is None or float(pf) < minimum_pf):
        reasons.append("PROFIT_FACTOR_GATE_FAILED")
    if positive_fraction < float(filters["minimum_positive_development_cell_fraction"]):
        reasons.append("POSITIVE_CELL_FRACTION_GATE_FAILED")
    if maximum_drawdown > float(filters["maximum_drawdown_fraction"]):
        reasons.append("MAXIMUM_DRAWDOWN_GATE_FAILED")
    if concentration > float(filters["maximum_single_trade_share_of_positive_pnl"]):
        reasons.append("TRADE_CONCENTRATION_GATE_FAILED")
    if total_stress_net <= 0.0:
        reasons.append("STRESS_NET_PNL_NOT_POSITIVE")
    if stress_expectancy <= 0.0:
        reasons.append("STRESS_EXPECTANCY_NOT_POSITIVE")

    record = {
        "schema": "YATL_HSSE_DEVELOPMENT_TRIAL",
        "schema_version": SCHEMA_VERSION,
        "implementation_id": IMPLEMENTATION_ID,
        "trial_id": f"HSSE002-{family}-{n1:04d}-{n2:04d}",
        "candidate_id": "RIE-CAND-0020",
        "family": family,
        "parameters": {"n1": n1, "n2": n2},
        "cell_count": len(cells),
        "completed_trades": total_completed,
        "completed_trades_by_symbol": per_symbol,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "base": {
            "total_net_pnl_after_costs_quote": _num(total_base_net),
            "realized_closed_trade_pnl_quote": _num(total_base_realized),
            "expectancy_quote": _num(expectancy),
            "profit_factor": pf,
            "profit_factor_infinite": pf_infinite,
            "gross_profit_quote": _num(gross_profit),
            "gross_loss_quote": _num(gross_loss),
            "largest_positive_trade_quote": _num(largest_positive),
            "largest_trade_profit_share": _num(concentration),
            "maximum_drawdown_fraction": _num(maximum_drawdown),
            "positive_development_cell_fraction": _num(positive_fraction),
            "median_development_cell_net_return_after_costs": _num(median_return),
            "lower_quartile_development_cell_net_return_after_costs": _num(
                lower_quartile
            ),
        },
        "stress": {
            "total_net_pnl_after_costs_quote": _num(total_stress_net),
            "realized_closed_trade_pnl_quote": _num(total_stress_realized),
            "expectancy_quote": _num(stress_expectancy),
        },
        "development_filter_precheck": {
            "status": (
                "ELIGIBLE_FOR_HSSE003_RECOMPUTE"
                if not reasons
                else "FILTERED_DEVELOPMENT"
            ),
            "failure_reasons": reasons,
            "neighbor_robustness_pending_hsse003": True,
            "exact_recompute_required_before_survivor_freeze": True,
        },
        "cells": cells,
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "p11_locked": True,
    }
    record["trial_sha256"] = _sha256(_canonical_json(record))
    return record


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finalize_ledger(
    *,
    root: Path,
    temporary: Path,
    family: str,
    trial_count: int,
    precheck_pass_count: int,
) -> dict[str, object]:
    digest = _file_sha256(temporary)
    target_dir = root / "historical-strategy-search" / "hsse-002"
    target_dir.mkdir(parents=True, exist_ok=True)
    final = target_dir / (
        f"development-ledger-{family.lower()}-{digest[:24]}.jsonl"
    )
    if final.exists():
        if _file_sha256(final) != digest:
            raise HSSESearchError("existing HSSE-002 ledger digest mismatch")
        temporary.unlink()
    else:
        os.replace(temporary, final)
        os.chmod(final, 0o600)
    return {
        "family": family,
        "trial_count": trial_count,
        "development_precheck_pass_count": precheck_pass_count,
        "ledger_relative_path": final.relative_to(root).as_posix(),
        "ledger_file_sha256": digest,
    }


def _write_index(root: Path, record: Mapping[str, object]) -> dict[str, str]:
    payload = _canonical_json(record)
    digest = _sha256(payload)
    directory = root / "historical-strategy-search" / "hsse-002"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"search-index-{digest[:24]}.json"
    if path.exists():
        if path.read_bytes() != payload:
            raise HSSESearchError("existing HSSE-002 index differs")
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    return {
        "index_relative_path": path.relative_to(root).as_posix(),
        "index_file_sha256": digest,
    }


def run_search(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
    plan_path: Path = DEFAULT_PLAN_PATH,
) -> dict[str, object]:
    plan, plan_sha, context = load_plan(plan_path)
    try:
        root = replay._safe_root(runtime_root)
        corpus = controls._load_control_corpus(
            runtime_root=root,
            quality_manifest_relative_path=quality_manifest_relative_path,
            quality_manifest_file_sha256=quality_manifest_file_sha256,
        )
    except (replay.ReplayError, controls.ControlError) as exc:
        raise HSSESearchError(str(exc)) from None
    if corpus.event_id != plan["data_scope"]["corpus_id"]:
        raise HSSESearchError("HSSE-002 loaded the wrong corpus")

    protocol = context["protocol"]
    folds = protocol["development_cross_validation"]["folds"]
    filters = protocol["development_survivor_filters"]
    series_by_symbol = {
        symbol: _series_for_symbol(corpus, symbol)
        for symbol in protocol["data_boundaries"]["symbols"]
    }
    windows = tuple(range(1, 1000, 10))
    pairs = _trial_pairs(windows)
    family_reports: list[dict[str, object]] = []

    outdir = root / "historical-strategy-search" / "hsse-002"
    outdir.mkdir(parents=True, exist_ok=True)
    for family in FAMILIES:
        print(
            f"HSSE-002 family={family} trials={len(pairs)} precompute=START",
            file=sys.stderr,
            flush=True,
        )
        indicators = {
            symbol: _indicator_grid(series, family, windows)
            for symbol, series in series_by_symbol.items()
        }
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{family.lower()}-",
            suffix=".jsonl.tmp",
            dir=outdir,
        )
        os.close(fd)
        temporary = Path(tmp_name)
        count = 0
        pass_count = 0
        try:
            with temporary.open("wb") as handle:
                for n1, n2 in pairs:
                    record = _trial(
                        family=family,
                        n1=n1,
                        n2=n2,
                        series_by_symbol=series_by_symbol,
                        indicators_by_symbol=indicators,
                        folds=folds,
                        execution=plan["execution_semantics"],
                        filters=filters,
                    )
                    line = _canonical_json(record)
                    handle.write(line)
                    count += 1
                    if (
                        record["development_filter_precheck"]["status"]
                        == "ELIGIBLE_FOR_HSSE003_RECOMPUTE"
                    ):
                        pass_count += 1
                    if count % 500 == 0:
                        print(
                            f"HSSE-002 family={family} progress={count}/{len(pairs)}",
                            file=sys.stderr,
                            flush=True,
                        )
                handle.flush()
                os.fsync(handle.fileno())
            family_reports.append(
                _finalize_ledger(
                    root=root,
                    temporary=temporary,
                    family=family,
                    trial_count=count,
                    precheck_pass_count=pass_count,
                )
            )
        except Exception:
            if temporary.exists():
                temporary.unlink()
            raise
        finally:
            del indicators
            gc.collect()

    if sum(item["trial_count"] for item in family_reports) != plan["trial_matrix"]["total_trials"]:
        raise HSSESearchError("HSSE-002 did not record the full trial matrix")

    index = {
        "schema": "YATL_HSSE_DEVELOPMENT_SEARCH_INDEX",
        "schema_version": SCHEMA_VERSION,
        "implementation_id": IMPLEMENTATION_ID,
        "plan_sha256": plan_sha,
        "candidate_id": plan["candidate_id"],
        "candidate_fingerprint_sha256": plan["candidate_fingerprint_sha256"],
        "quality_manifest_relative_path": quality_manifest_relative_path,
        "quality_manifest_file_sha256": quality_manifest_file_sha256,
        "source_corpus_id": corpus.event_id,
        "family_count": len(family_reports),
        "total_trial_count": sum(item["trial_count"] for item in family_reports),
        "development_precheck_pass_count": sum(
            item["development_precheck_pass_count"] for item in family_reports
        ),
        "families": family_reports,
        "ranking_performed": False,
        "survivor_selected": False,
        "blind_oos_read": False,
        "audit_holdout_read": False,
        "numeric_policy": plan["numeric_policy"],
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
        "p11_locked": True,
    }
    index["result_sha256"] = _sha256(_canonical_json(index))
    artifact = _write_index(root, index)
    return {
        "implementation_id": IMPLEMENTATION_ID,
        "candidate_id": plan["candidate_id"],
        "family_count": index["family_count"],
        "total_trial_count": index["total_trial_count"],
        "development_precheck_pass_count": index[
            "development_precheck_pass_count"
        ],
        "families": family_reports,
        **artifact,
        "result_sha256": index["result_sha256"],
        "ranking_performed": False,
        "survivor_selected": False,
        "blind_oos_read": False,
        "audit_holdout_read": False,
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "p11_locked": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research.historical_strategy_search.trend_ma",
        description="HSSE-002 deterministic Development-only trend MA search",
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--quality-manifest", required=True)
    parser.add_argument("--quality-manifest-sha256", required=True)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument(
        "--validate-plan-only",
        action="store_true",
        help="validate bindings and trial matrix without reading market data",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.validate_plan_only:
        plan, plan_sha, _ = load_plan(args.plan)
        result = {
            "implementation_id": IMPLEMENTATION_ID,
            "plan_id": plan["plan_id"],
            "plan_sha256": plan_sha,
            "family_count": len(plan["trial_matrix"]["family_order"]),
            "total_trial_count": plan["trial_matrix"]["total_trials"],
            "research_only": True,
            "p10_write_allowed": False,
            "p11_locked": True,
        }
    else:
        result = run_search(
            runtime_root=args.runtime_root,
            quality_manifest_relative_path=args.quality_manifest,
            quality_manifest_file_sha256=args.quality_manifest_sha256,
            plan_path=args.plan,
        )
    print(_json(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HSSESearchError as exc:
        print(
            _json(
                {
                    "code": "HSSE002_SEARCH_ERROR",
                    "reason": str(exc),
                    "research_only": True,
                    "p10_write_allowed": False,
                    "p11_locked": True,
                }
            )
        )
        raise SystemExit(2)
