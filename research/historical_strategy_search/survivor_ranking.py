"""HSSE-003 exact Development recomputation and survivor ranking.

Consumes only the immutable HSSE-002 Development ledgers registered in the
HSSE-003 protocol. It exact-recomputes the 16 Development precheck candidates
with Decimal-256 economics, checks immediate parameter-neighborhood stability,
and deterministically proposes candidates for a later HSSE-004 freeze.

It does not read Blind OOS or final-audit data and grants no trading authority.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from statistics import median
from typing import Mapping, Sequence

from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.data import INTERVAL_MILLISECONDS

from research.crisis_lab import controls, replay

from . import trend_ma as hsse2


IMPLEMENTATION_ID = "HSSE-003-SURVIVOR-RANKING/0.1.0"
SCHEMA_VERSION = "0.1.0"
DEFAULT_PROTOCOL_PATH = Path(
    "docs/research/historical-strategy-search/"
    "HSSE-003-SURVIVOR-RANKING-PROTOCOL-v0.1.0.json"
)
MAX_PROTOCOL_BYTES = 1024 * 1024
MAX_INDEX_BYTES = 4 * 1024 * 1024
MAX_LEDGER_BYTES = 128 * 1024 * 1024
HOUR_MS = INTERVAL_MILLISECONDS["1h"]


class HSSESurvivorError(RuntimeError):
    """HSSE-003 violated an evidence, accounting, or ranking boundary."""


@dataclass(frozen=True, slots=True)
class ExactSeries:
    symbol: str
    times: tuple[int, ...]
    opens: tuple[str, ...]
    closes: tuple[str, ...]


@dataclass(slots=True)
class _Account:
    cash: Decimal
    entry_debit: Decimal | None
    realized: list[Decimal]
    total_fee: Decimal
    total_slippage: Decimal


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
        raise HSSESurvivorError("HSSE-003 Decimal arithmetic is not finite")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _number(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception:
        raise HSSESurvivorError(f"{label} is not numeric") from None
    if not result.is_finite():
        raise HSSESurvivorError(f"{label} is not finite")
    return result


def _time_ms(value: object, label: str) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise HSSESurvivorError(f"{label} is not UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise HSSESurvivorError(f"{label} is invalid") from None
    return int(parsed.timestamp() * 1000)


def _read_json(path: Path, maximum: int, label: str) -> tuple[dict[str, object], bytes]:
    if path.is_symlink():
        raise HSSESurvivorError(f"symlink {label} is forbidden")
    try:
        payload = path.read_bytes()
    except OSError:
        raise HSSESurvivorError(f"cannot read {label}") from None
    if not payload or len(payload) > maximum:
        raise HSSESurvivorError(f"{label} size is invalid")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HSSESurvivorError(f"{label} is not UTF-8 JSON") from None
    if not isinstance(record, dict):
        raise HSSESurvivorError(f"{label} must be an object")
    return record, payload


def validate_protocol(
    path: Path = DEFAULT_PROTOCOL_PATH,
) -> tuple[dict[str, object], str]:
    record, payload = _read_json(path, MAX_PROTOCOL_BYTES, "HSSE-003 protocol")
    if (
        record.get("schema") != "YATL_HSSE_SURVIVOR_RANKING_PROTOCOL"
        or record.get("schema_version") != SCHEMA_VERSION
        or record.get("protocol_id") != "HSSE-003-SURVIVOR-RANKING-001"
        or record.get("status")
        != "REGISTERED_AFTER_HSSE002_OUTCOME_BEFORE_HSSE003_RECOMPUTE"
        or record.get("research_only") is not True
        or record.get("p10_read") is not False
        or record.get("p10_write_allowed") is not False
        or record.get("p10_evidence_effect") != "NONE"
        or record.get("live_master_lock") != "OFF"
        or record.get("trade_permission") is not False
        or record.get("order_endpoint") is not False
        or record.get("quantity_authority") is not False
        or record.get("risk_authorization_mutation") is not False
        or record.get("ai_direct_execution") is not False
        or record.get("p11_locked") is not True
    ):
        raise HSSESurvivorError("HSSE-003 safety invariants are invalid")

    source = record.get("input_search")
    exact = record.get("exact_recompute")
    gate = record.get("exact_gate")
    neighbor = record.get("neighbor_robustness")
    ranking = record.get("ranking")
    output = record.get("output")
    if not all(
        isinstance(x, dict)
        for x in (source, exact, gate, neighbor, ranking, output)
    ):
        raise HSSESurvivorError("HSSE-003 protocol scope is incomplete")

    ledgers = source.get("ledgers")
    if (
        source.get("implementation_id") != hsse2.IMPLEMENTATION_ID
        or source.get("candidate_id") != "RIE-CAND-0020"
        or source.get("final_head_sha")
        != "2b6354b5ea491b45ce460b76361da9d24e5e3b0d"
        or source.get("total_trial_count") != 14850
        or source.get("development_precheck_pass_count") != 16
        or not isinstance(ledgers, list)
        or len(ledgers) != 3
    ):
        raise HSSESurvivorError("HSSE-003 input search identity is invalid")
    expected_families = list(hsse2.FAMILIES)
    if [x.get("family") for x in ledgers if isinstance(x, dict)] != expected_families:
        raise HSSESurvivorError("HSSE-003 ledger family order is invalid")
    if sum(int(x.get("trial_count", -1)) for x in ledgers) != 14850:
        raise HSSESurvivorError("HSSE-003 ledger trial counts are invalid")
    if sum(int(x.get("development_precheck_pass_count", -1)) for x in ledgers) != 16:
        raise HSSESurvivorError("HSSE-003 precheck counts are invalid")
    for item in ledgers:
        if (
            not isinstance(item.get("relative_path"), str)
            or not isinstance(item.get("file_sha256"), str)
            or len(item["file_sha256"]) != 64
            or item.get("trial_count") != 4950
        ):
            raise HSSESurvivorError("HSSE-003 ledger binding is invalid")
    index = source.get("index")
    if (
        not isinstance(index, dict)
        or not isinstance(index.get("relative_path"), str)
        or not isinstance(index.get("file_sha256"), str)
        or len(index["file_sha256"]) != 64
    ):
        raise HSSESurvivorError("HSSE-003 index binding is invalid")

    if (
        exact.get("candidate_set") != "ONLY_HSSE002_DEVELOPMENT_PRECHECK_PASS"
        or exact.get("expected_candidate_count") != 16
        or exact.get("signal_semantics")
        != "REUSE_FROZEN_HSSE002_SOURCE_FIDELITY_BINARY64_MOVING_AVERAGE_SIGNALS"
        or exact.get("economic_arithmetic") != "DECIMAL_256"
        or exact.get("price_inputs") != "ORIGINAL_CANONICAL_DECIMAL_STRINGS"
        or exact.get("next_open_execution") is not True
        or exact.get("base_fee_bps") != "10"
        or exact.get("base_adverse_slippage_bps") != "5"
        or exact.get("stress_fee_bps") != "20"
        or exact.get("stress_adverse_slippage_bps") != "10"
        or exact.get("quantity") != "0.001"
        or exact.get("initial_equity_quote") != "10000"
        or exact.get("binary64_search_result_is_authoritative") is not False
        or exact.get("exact_recompute_is_authoritative") is not True
    ):
        raise HSSESurvivorError("HSSE-003 exact recompute contract is invalid")

    if (
        neighbor.get("grid_step") != 10
        or neighbor.get("neighborhood") != "IMMEDIATE_AXIAL_SAME_FAMILY"
        or neighbor.get("offsets") != [[-10, 0], [10, 0], [0, -10], [0, 10]]
        or neighbor.get("minimum_valid_neighbors") != 2
        or neighbor.get("minimum_neighbor_pass_fraction") != "0.50"
    ):
        raise HSSESurvivorError("HSSE-003 neighbor contract is invalid")
    nrules = neighbor.get("neighbor_pass_rules")
    if (
        not isinstance(nrules, dict)
        or nrules.get("minimum_profit_factor_after_base_costs") != "1.02"
        or nrules.get("minimum_positive_development_cell_fraction") != "0.50"
        or nrules.get("require_positive_total_net_pnl_after_base_costs") is not True
        or nrules.get("require_positive_expectancy_after_base_costs") is not True
        or nrules.get("cost_stress_requires_positive_net_pnl") is not True
    ):
        raise HSSESurvivorError("HSSE-003 neighbor pass rules are invalid")

    if (
        ranking.get("input") != "EXACT_GATE_AND_NEIGHBOR_ROBUSTNESS_PASS_ONLY"
        or ranking.get("family_survivor_cap") != 3
        or ranking.get("overall_survivor_cap") != 12
        or ranking.get("survivor_count_is_a_cap_not_a_quota") is not True
        or ranking.get("no_candidate_pass_is_valid") is not True
    ):
        raise HSSESurvivorError("HSSE-003 ranking contract is invalid")
    if (
        output.get("retain_all_16_exact_recomputations") is not True
        or output.get("retain_neighbor_evidence") is not True
        or output.get("proposed_survivors_are_not_frozen_hsse004_candidates")
        is not True
        or output.get("blind_oos_read") is not False
        or output.get("audit_holdout_read") is not False
    ):
        raise HSSESurvivorError("HSSE-003 output isolation is invalid")

    return record, _sha256(payload)


def _safe_artifact_path(root: Path, relative: str) -> Path:
    try:
        safe_root = replay._safe_root(root)
    except replay.ReplayError as exc:
        raise HSSESurvivorError(str(exc)) from None
    target = (safe_root / relative).resolve()
    if not target.is_relative_to(safe_root.resolve()):
        raise HSSESurvivorError("HSSE-003 artifact path escapes runtime root")
    if target.is_symlink():
        raise HSSESurvivorError("symlink HSSE artifact is forbidden")
    return target


def _file_sha256(path: Path, maximum: int, label: str) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        raise HSSESurvivorError(f"cannot stat {label}") from None
    if size <= 0 or size > maximum:
        raise HSSESurvivorError(f"{label} size is invalid")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        raise HSSESurvivorError(f"cannot read {label}") from None
    return digest.hexdigest()


def _validate_trial_record(record: object, family: str) -> dict[str, object]:
    if not isinstance(record, dict):
        raise HSSESurvivorError("HSSE-002 ledger line is not an object")
    if (
        record.get("schema") != "YATL_HSSE_DEVELOPMENT_TRIAL"
        or record.get("schema_version") != hsse2.SCHEMA_VERSION
        or record.get("implementation_id") != hsse2.IMPLEMENTATION_ID
        or record.get("candidate_id") != "RIE-CAND-0020"
        or record.get("family") != family
        or record.get("research_only") is not True
        or record.get("p10_read") is not False
        or record.get("p10_write_allowed") is not False
        or record.get("p10_evidence_effect") != "NONE"
        or record.get("p11_locked") is not True
    ):
        raise HSSESurvivorError("HSSE-002 trial identity/safety is invalid")
    claimed = record.get("trial_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise HSSESurvivorError("HSSE-002 trial digest is invalid")
    body = dict(record)
    del body["trial_sha256"]
    if _sha256(_canonical_json(body)) != claimed:
        raise HSSESurvivorError("HSSE-002 trial digest mismatch")
    params = record.get("parameters")
    if (
        not isinstance(params, dict)
        or type(params.get("n1")) is not int
        or type(params.get("n2")) is not int
        or params["n1"] not in range(1, 1000, 10)
        or params["n2"] not in range(1, 1000, 10)
        or params["n1"] >= params["n2"]
    ):
        raise HSSESurvivorError("HSSE-002 trial parameters are invalid")
    expected_id = f"HSSE002-{family}-{params['n1']:04d}-{params['n2']:04d}"
    if record.get("trial_id") != expected_id:
        raise HSSESurvivorError("HSSE-002 trial id is invalid")
    return record


def _load_ledger(
    root: Path,
    binding: Mapping[str, object],
) -> dict[tuple[int, int], dict[str, object]]:
    family = str(binding["family"])
    path = _safe_artifact_path(root, str(binding["relative_path"]))
    if _file_sha256(path, MAX_LEDGER_BYTES, f"{family} ledger") != binding["file_sha256"]:
        raise HSSESurvivorError(f"{family} ledger SHA-256 mismatch")
    records: dict[tuple[int, int], dict[str, object]] = {}
    pass_count = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.endswith("\n") or not line.strip():
                    raise HSSESurvivorError("HSSE-002 ledger line framing is invalid")
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    raise HSSESurvivorError("HSSE-002 ledger JSONL is invalid") from None
                valid = _validate_trial_record(record, family)
                p = valid["parameters"]
                key = (p["n1"], p["n2"])
                if key in records:
                    raise HSSESurvivorError("HSSE-002 ledger has duplicate trial")
                records[key] = valid
                if (
                    valid["development_filter_precheck"]["status"]
                    == "ELIGIBLE_FOR_HSSE003_RECOMPUTE"
                ):
                    pass_count += 1
    except OSError:
        raise HSSESurvivorError(f"cannot read {family} ledger") from None

    expected_pairs = set(hsse2._trial_pairs(tuple(range(1, 1000, 10))))
    if set(records) != expected_pairs:
        raise HSSESurvivorError(f"{family} ledger does not contain exact grid")
    if len(records) != binding["trial_count"] or pass_count != binding["development_precheck_pass_count"]:
        raise HSSESurvivorError(f"{family} ledger counts differ from registration")
    return records


def _load_search_artifacts(
    root: Path, protocol: Mapping[str, object]
) -> tuple[
    dict[str, dict[tuple[int, int], dict[str, object]]],
    dict[str, object],
]:
    source = protocol["input_search"]
    index_binding = source["index"]
    index_path = _safe_artifact_path(root, index_binding["relative_path"])
    if _file_sha256(index_path, MAX_INDEX_BYTES, "HSSE-002 index") != index_binding["file_sha256"]:
        raise HSSESurvivorError("HSSE-002 index SHA-256 mismatch")
    index, _ = _read_json(index_path, MAX_INDEX_BYTES, "HSSE-002 index")
    if (
        index.get("schema") != "YATL_HSSE_DEVELOPMENT_SEARCH_INDEX"
        or index.get("implementation_id") != source["implementation_id"]
        or index.get("candidate_id") != source["candidate_id"]
        or index.get("total_trial_count") != source["total_trial_count"]
        or index.get("development_precheck_pass_count")
        != source["development_precheck_pass_count"]
        or index.get("result_sha256") != source["result_sha256"]
        or index.get("ranking_performed") is not False
        or index.get("survivor_selected") is not False
        or index.get("blind_oos_read") is not False
        or index.get("audit_holdout_read") is not False
    ):
        raise HSSESurvivorError("HSSE-002 index identity is invalid")
    body = dict(index)
    claimed_result = body.pop("result_sha256")
    if _sha256(_canonical_json(body)) != claimed_result:
        raise HSSESurvivorError("HSSE-002 index result digest mismatch")

    ledgers = {
        item["family"]: _load_ledger(root, item)
        for item in source["ledgers"]
    }
    return ledgers, index


def _exact_series(corpus: controls.AdmittedControlCorpus, symbol: str) -> ExactSeries:
    candles = corpus.datasets.get((symbol, "1h"))
    if not candles:
        raise HSSESurvivorError(f"missing 1h Development data for {symbol}")
    times = tuple(c.open_time_ms for c in candles)
    if (
        times != tuple(sorted(times))
        or len(times) != len(set(times))
        or any(not c.is_closed for c in candles)
    ):
        raise HSSESurvivorError(f"invalid exact series for {symbol}")
    return ExactSeries(
        symbol=symbol,
        times=times,
        opens=tuple(c.open for c in candles),
        closes=tuple(c.close for c in candles),
    )


def _new_account(initial: Decimal) -> _Account:
    return _Account(
        cash=initial,
        entry_debit=None,
        realized=[],
        total_fee=Decimal(0),
        total_slippage=Decimal(0),
    )


def _entry(
    account: _Account,
    *,
    reference: Decimal,
    quantity: Decimal,
    fee_bps: Decimal,
    slippage_bps: Decimal,
) -> None:
    if account.entry_debit is not None:
        raise HSSESurvivorError("HSSE-003 overlapping exact entry")
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        fee_rate = fee_bps / Decimal(10000)
        slip_rate = slippage_bps / Decimal(10000)
        execution = reference * (Decimal(1) + slip_rate)
        gross = quantity * execution
        fee = gross * fee_rate
        slippage = quantity * (execution - reference)
        debit = gross + fee
        cash = account.cash - debit
    if cash < 0:
        raise HSSESurvivorError("HSSE-003 exact account has insufficient cash")
    account.cash = cash
    account.entry_debit = debit
    account.total_fee += fee
    account.total_slippage += slippage


def _exit(
    account: _Account,
    *,
    reference: Decimal,
    quantity: Decimal,
    fee_bps: Decimal,
    slippage_bps: Decimal,
) -> None:
    if account.entry_debit is None:
        raise HSSESurvivorError("HSSE-003 exact exit has no entry")
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        fee_rate = fee_bps / Decimal(10000)
        slip_rate = slippage_bps / Decimal(10000)
        execution = reference * (Decimal(1) - slip_rate)
        gross = quantity * execution
        fee = gross * fee_rate
        slippage = quantity * (reference - execution)
        proceeds = gross - fee
        pnl = proceeds - account.entry_debit
        cash = account.cash + proceeds
    account.cash = cash
    account.realized.append(pnl)
    account.entry_debit = None
    account.total_fee += fee
    account.total_slippage += slippage


def _equity(
    account: _Account,
    *,
    mark: Decimal,
    quantity: Decimal,
    fee_bps: Decimal,
    slippage_bps: Decimal,
) -> Decimal:
    if account.entry_debit is None:
        return account.cash
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        fee_rate = fee_bps / Decimal(10000)
        slip_rate = slippage_bps / Decimal(10000)
        execution = mark * (Decimal(1) - slip_rate)
        gross = quantity * execution
        liquidation = gross * (Decimal(1) - fee_rate)
        return account.cash + liquidation


def _exact_cell(
    *,
    exact: ExactSeries,
    signal: hsse2.SearchSeries,
    short_values,
    long_values,
    start_ms: int,
    end_ms: int,
    exact_policy: Mapping[str, object],
) -> dict[str, object]:
    if exact.times != signal.times:
        raise HSSESurvivorError("exact and signal series timestamps differ")
    start = bisect.bisect_left(exact.times, start_ms)
    end = bisect.bisect_left(exact.times, end_ms)
    if start >= end:
        raise HSSESurvivorError("HSSE-003 exact cell is empty")

    quantity = Decimal(exact_policy["quantity"])
    initial = Decimal(exact_policy["initial_equity_quote"])
    base_fee = Decimal(exact_policy["base_fee_bps"])
    base_slip = Decimal(exact_policy["base_adverse_slippage_bps"])
    stress_fee = Decimal(exact_policy["stress_fee_bps"])
    stress_slip = Decimal(exact_policy["stress_adverse_slippage_bps"])
    base = _new_account(initial)
    stress = _new_account(initial)
    position = False
    missing = 0
    entry_fills = 0
    exit_fills = 0
    peak = initial
    maximum_drawdown = Decimal(0)

    for i in range(start, end):
        mark = Decimal(exact.closes[i])
        equity = _equity(
            base,
            mark=mark,
            quantity=quantity,
            fee_bps=base_fee,
            slippage_bps=base_slip,
        )
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak
        if drawdown > maximum_drawdown:
            maximum_drawdown = drawdown

        if i == 0:
            continue
        values = (
            short_values[i],
            long_values[i],
            short_values[i - 1],
            long_values[i - 1],
        )
        if not all(math.isfinite(v) for v in values):
            continue
        short_now, long_now, short_prev, long_prev = values
        enter = (not position) and short_now > long_now and short_prev <= long_prev
        exit_ = position and short_now < long_now and short_prev >= long_prev
        if not enter and not exit_:
            continue
        fill_i = i + 1
        if (
            fill_i >= end
            or fill_i >= len(exact.times)
            or exact.times[fill_i] != exact.times[i] + HOUR_MS
        ):
            missing += 1
            continue
        reference = Decimal(exact.opens[fill_i])
        if enter:
            _entry(
                base,
                reference=reference,
                quantity=quantity,
                fee_bps=base_fee,
                slippage_bps=base_slip,
            )
            _entry(
                stress,
                reference=reference,
                quantity=quantity,
                fee_bps=stress_fee,
                slippage_bps=stress_slip,
            )
            position = True
            entry_fills += 1
        else:
            _exit(
                base,
                reference=reference,
                quantity=quantity,
                fee_bps=base_fee,
                slippage_bps=base_slip,
            )
            _exit(
                stress,
                reference=reference,
                quantity=quantity,
                fee_bps=stress_fee,
                slippage_bps=stress_slip,
            )
            position = False
            exit_fills += 1

    final_mark = Decimal(exact.closes[end - 1])
    base_final = _equity(
        base,
        mark=final_mark,
        quantity=quantity,
        fee_bps=base_fee,
        slippage_bps=base_slip,
    )
    stress_final = _equity(
        stress,
        mark=final_mark,
        quantity=quantity,
        fee_bps=stress_fee,
        slippage_bps=stress_slip,
    )
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        final_dd = (peak - base_final) / peak
    maximum_drawdown = max(maximum_drawdown, final_dd)

    realized = _sum(base.realized)
    stress_realized = _sum(stress.realized)
    wins = [x for x in base.realized if x > 0]
    losses = [x for x in base.realized if x < 0]
    gross_profit = _sum(wins)
    gross_loss = -_sum(losses)
    completed = len(base.realized)
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        base_net = base_final - initial
        stress_net = stress_final - initial
        base_return = base_net / initial
        stress_return = stress_net / initial

    return {
        "completed_trades": completed,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": completed - len(wins) - len(losses),
        "entry_fills": entry_fills,
        "exit_fills": exit_fills,
        "missing_fill_signals": missing,
        "open_position_at_end": position,
        "base": {
            "net_pnl_after_costs_quote": _plain(base_net),
            "net_return_after_costs": _plain(base_return),
            "realized_closed_trade_pnl_quote": _plain(realized),
            "gross_profit_quote": _plain(gross_profit),
            "gross_loss_quote": _plain(gross_loss),
            "largest_positive_trade_quote": _plain(max(wins) if wins else Decimal(0)),
            "executed_fee_quote": _plain(base.total_fee),
            "executed_slippage_quote": _plain(base.total_slippage),
            "maximum_drawdown_fraction": _plain(maximum_drawdown),
        },
        "stress": {
            "net_pnl_after_costs_quote": _plain(stress_net),
            "net_return_after_costs": _plain(stress_return),
            "realized_closed_trade_pnl_quote": _plain(stress_realized),
        },
    }


def _sum(values: Sequence[Decimal]) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        result = Decimal(0)
        for value in values:
            result += value
        return result


def _median_decimal(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise HSSESurvivorError("cannot compute median of empty values")
    ordered = sorted(values)
    n = len(ordered)
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        if n % 2:
            return ordered[n // 2]
        return (ordered[n // 2 - 1] + ordered[n // 2]) / Decimal(2)


def _lower_quartile(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    if not ordered:
        raise HSSESurvivorError("cannot compute lower quartile")
    lower = ordered[: len(ordered) // 2]
    return _median_decimal(lower if lower else ordered)


def _profit_factor(
    gross_profit: Decimal, gross_loss: Decimal
) -> tuple[str | None, bool, Decimal | None]:
    if gross_loss == 0:
        return None, gross_profit > 0, None
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        value = gross_profit / gross_loss
    return _plain(value), False, value


def _exact_candidate(
    *,
    search_record: Mapping[str, object],
    corpus: controls.AdmittedControlCorpus,
    folds: Sequence[Mapping[str, object]],
    exact_policy: Mapping[str, object],
    gate: Mapping[str, object],
    signal_cache: dict[tuple[str, str, int], object],
    signal_series: Mapping[str, hsse2.SearchSeries],
    exact_series: Mapping[str, ExactSeries],
) -> dict[str, object]:
    family = str(search_record["family"])
    n1 = int(search_record["parameters"]["n1"])
    n2 = int(search_record["parameters"]["n2"])

    for symbol, series in signal_series.items():
        for window in (n1, n2):
            key = (symbol, family, window)
            if key not in signal_cache:
                signal_cache[key] = hsse2._indicator_series(series, family, window)

    cells = []
    per_symbol = {symbol: 0 for symbol in sorted(signal_series)}
    total_completed = wins = losses = 0
    net_values: list[Decimal] = []
    stress_values: list[Decimal] = []
    cell_returns: list[Decimal] = []
    gross_profit = Decimal(0)
    gross_loss = Decimal(0)
    largest_positive = Decimal(0)
    realized_values: list[Decimal] = []
    stress_realized_values: list[Decimal] = []
    max_drawdown = Decimal(0)
    positive_cells = 0

    for fold in folds:
        start_ms = _time_ms(fold["evaluation_start_utc"], "fold start")
        end_ms = _time_ms(fold["evaluation_end_exclusive_utc"], "fold end")
        for symbol in sorted(signal_series):
            cell = _exact_cell(
                exact=exact_series[symbol],
                signal=signal_series[symbol],
                short_values=signal_cache[(symbol, family, n1)],
                long_values=signal_cache[(symbol, family, n2)],
                start_ms=start_ms,
                end_ms=end_ms,
                exact_policy=exact_policy,
            )
            base = cell["base"]
            stress = cell["stress"]
            completed = int(cell["completed_trades"])
            total_completed += completed
            wins += int(cell["wins"])
            losses += int(cell["losses"])
            per_symbol[symbol] += completed
            net = _number(base["net_pnl_after_costs_quote"], "exact net")
            stress_net = _number(stress["net_pnl_after_costs_quote"], "stress net")
            net_values.append(net)
            stress_values.append(stress_net)
            realized_values.append(
                _number(base["realized_closed_trade_pnl_quote"], "exact realized")
            )
            stress_realized_values.append(
                _number(
                    stress["realized_closed_trade_pnl_quote"],
                    "stress exact realized",
                )
            )
            gp = _number(base["gross_profit_quote"], "gross profit")
            gl = _number(base["gross_loss_quote"], "gross loss")
            gross_profit += gp
            gross_loss += gl
            largest_positive = max(
                largest_positive,
                _number(base["largest_positive_trade_quote"], "largest trade"),
            )
            dd = _number(base["maximum_drawdown_fraction"], "drawdown")
            max_drawdown = max(max_drawdown, dd)
            ret = _number(base["net_return_after_costs"], "cell return")
            cell_returns.append(ret)
            if net > 0:
                positive_cells += 1
            cells.append(
                {
                    "fold_id": fold["fold_id"],
                    "symbol": symbol,
                    "completed_trades": completed,
                    "base_net_return_after_costs": base["net_return_after_costs"],
                    "stress_net_return_after_costs": stress["net_return_after_costs"],
                    "maximum_drawdown_fraction": base["maximum_drawdown_fraction"],
                }
            )

    total_net = _sum(net_values)
    total_stress_net = _sum(stress_values)
    realized = _sum(realized_values)
    stress_realized = _sum(stress_realized_values)
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        expectancy = (
            realized / Decimal(total_completed) if total_completed else Decimal(0)
        )
        stress_expectancy = (
            stress_realized / Decimal(total_completed)
            if total_completed
            else Decimal(0)
        )
        positive_fraction = Decimal(positive_cells) / Decimal(len(cells))
        concentration = (
            largest_positive / gross_profit
            if gross_profit > 0
            else Decimal(0)
        )
    pf_text, pf_infinite, pf_value = _profit_factor(gross_profit, gross_loss)
    median_return = _median_decimal(cell_returns)
    lower_q = _lower_quartile(cell_returns)

    reasons = []
    if total_completed < int(gate["minimum_completed_trades_total"]):
        reasons.append("MINIMUM_COMPLETED_TRADES_TOTAL")
    if any(
        count < int(gate["minimum_completed_trades_per_symbol"])
        for count in per_symbol.values()
    ):
        reasons.append("MINIMUM_COMPLETED_TRADES_PER_SYMBOL")
    if total_net <= 0:
        reasons.append("TOTAL_NET_PNL_NOT_POSITIVE")
    if expectancy <= 0:
        reasons.append("EXPECTANCY_NOT_POSITIVE")
    minimum_pf = Decimal(gate["minimum_profit_factor_after_base_costs"])
    if not pf_infinite and (pf_value is None or pf_value < minimum_pf):
        reasons.append("PROFIT_FACTOR_GATE_FAILED")
    if positive_fraction < Decimal(
        gate["minimum_positive_development_cell_fraction"]
    ):
        reasons.append("POSITIVE_CELL_FRACTION_GATE_FAILED")
    if max_drawdown > Decimal(gate["maximum_drawdown_fraction"]):
        reasons.append("MAXIMUM_DRAWDOWN_GATE_FAILED")
    if concentration > Decimal(
        gate["maximum_single_trade_share_of_positive_pnl"]
    ):
        reasons.append("TRADE_CONCENTRATION_GATE_FAILED")
    if total_stress_net <= 0:
        reasons.append("STRESS_NET_PNL_NOT_POSITIVE")
    if stress_expectancy <= 0:
        reasons.append("STRESS_EXPECTANCY_NOT_POSITIVE")

    return {
        "trial_id": search_record["trial_id"],
        "family": family,
        "parameters": {"n1": n1, "n2": n2},
        "search_trial_sha256": search_record["trial_sha256"],
        "completed_trades": total_completed,
        "completed_trades_by_symbol": per_symbol,
        "wins": wins,
        "losses": losses,
        "base": {
            "total_net_pnl_after_costs_quote": _plain(total_net),
            "realized_closed_trade_pnl_quote": _plain(realized),
            "expectancy_quote": _plain(expectancy),
            "profit_factor": pf_text,
            "profit_factor_infinite": pf_infinite,
            "gross_profit_quote": _plain(gross_profit),
            "gross_loss_quote": _plain(gross_loss),
            "largest_positive_trade_quote": _plain(largest_positive),
            "largest_trade_profit_share": _plain(concentration),
            "maximum_drawdown_fraction": _plain(max_drawdown),
            "positive_development_cell_fraction": _plain(positive_fraction),
            "median_development_cell_net_return_after_costs": _plain(
                median_return
            ),
            "lower_quartile_development_cell_net_return_after_costs": _plain(
                lower_q
            ),
        },
        "stress": {
            "total_net_pnl_after_costs_quote": _plain(total_stress_net),
            "realized_closed_trade_pnl_quote": _plain(stress_realized),
            "expectancy_quote": _plain(stress_expectancy),
        },
        "exact_gate": {
            "status": "PASS" if not reasons else "FAIL",
            "failure_reasons": reasons,
        },
        "cells": cells,
    }


def _neighbor_pass(
    record: Mapping[str, object], rules: Mapping[str, object]
) -> bool:
    base = record["base"]
    stress = record["stress"]
    if _number(base["total_net_pnl_after_costs_quote"], "neighbor net") <= 0:
        return False
    if _number(base["expectancy_quote"], "neighbor expectancy") <= 0:
        return False
    if base["profit_factor_infinite"] is not True:
        pf = base["profit_factor"]
        if pf is None or _number(pf, "neighbor pf") < Decimal(
            rules["minimum_profit_factor_after_base_costs"]
        ):
            return False
    if _number(
        base["positive_development_cell_fraction"], "neighbor cells"
    ) < Decimal(rules["minimum_positive_development_cell_fraction"]):
        return False
    if _number(stress["total_net_pnl_after_costs_quote"], "neighbor stress") <= 0:
        return False
    return True


def _neighbor_evidence(
    family: str,
    n1: int,
    n2: int,
    records: Mapping[tuple[int, int], Mapping[str, object]],
    neighbor_protocol: Mapping[str, object],
) -> dict[str, object]:
    offsets = neighbor_protocol["offsets"]
    valid = []
    passing = []
    grid = set(range(1, 1000, 10))
    for dn1, dn2 in offsets:
        pair = (n1 + dn1, n2 + dn2)
        if pair[0] not in grid or pair[1] not in grid or pair[0] >= pair[1]:
            continue
        trial = records.get(pair)
        if trial is None:
            raise HSSESurvivorError("registered neighbor is missing from ledger")
        valid.append(trial["trial_id"])
        if _neighbor_pass(trial, neighbor_protocol["neighbor_pass_rules"]):
            passing.append(trial["trial_id"])
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        fraction = (
            Decimal(len(passing)) / Decimal(len(valid))
            if valid
            else Decimal(0)
        )
    passed = (
        len(valid) >= int(neighbor_protocol["minimum_valid_neighbors"])
        and fraction
        >= Decimal(neighbor_protocol["minimum_neighbor_pass_fraction"])
    )
    return {
        "family": family,
        "valid_neighbor_count": len(valid),
        "passing_neighbor_count": len(passing),
        "neighbor_pass_fraction": _plain(fraction),
        "valid_neighbor_trial_ids": valid,
        "passing_neighbor_trial_ids": passing,
        "status": "PASS" if passed else "FAIL",
    }


def _pf_rank(candidate: Mapping[str, object]) -> Decimal:
    base = candidate["base"]
    if base["profit_factor_infinite"] is True:
        return Decimal("1E100")
    return _number(base["profit_factor"], "ranking PF")


def _vector(candidate: Mapping[str, object]) -> tuple[Decimal, ...]:
    base = candidate["base"]
    stress = candidate["stress"]
    neighbor = candidate["neighbor_robustness"]
    return (
        _number(
            base["median_development_cell_net_return_after_costs"],
            "median return",
        ),
        _number(
            base["lower_quartile_development_cell_net_return_after_costs"],
            "lower quartile",
        ),
        _pf_rank(candidate),
        -_number(base["maximum_drawdown_fraction"], "drawdown"),
        _number(stress["total_net_pnl_after_costs_quote"], "stress net"),
        _number(neighbor["neighbor_pass_fraction"], "neighbor fraction"),
    )


def _dominates(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    a = _vector(left)
    b = _vector(right)
    return all(x >= y for x, y in zip(a, b)) and any(
        x > y for x, y in zip(a, b)
    )


def _tie_key(
    candidate: Mapping[str, object],
    complexity: Mapping[str, object],
) -> tuple[object, ...]:
    base = candidate["base"]
    return (
        -_number(
            base["lower_quartile_development_cell_net_return_after_costs"],
            "tie lower quartile",
        ),
        -_number(
            base["median_development_cell_net_return_after_costs"],
            "tie median",
        ),
        -_pf_rank(candidate),
        _number(base["maximum_drawdown_fraction"], "tie drawdown"),
        int(complexity[candidate["family"]]),
        _number(base["largest_trade_profit_share"], "tie concentration"),
        candidate["family"],
        candidate["parameters"]["n1"],
        candidate["parameters"]["n2"],
    )


def _rank(
    candidates: Sequence[dict[str, object]],
    ranking: Mapping[str, object],
) -> tuple[list[dict[str, object]], list[str]]:
    eligible = [
        item
        for item in candidates
        if item["exact_gate"]["status"] == "PASS"
        and item["neighbor_robustness"]["status"] == "PASS"
    ]
    frontier = [
        item
        for item in eligible
        if not any(
            _dominates(other, item)
            for other in eligible
            if other["trial_id"] != item["trial_id"]
        )
    ]
    ordered = sorted(
        frontier,
        key=lambda item: _tie_key(item, ranking["family_complexity"]),
    )
    family_counts = {family: 0 for family in hsse2.FAMILIES}
    selected = []
    for item in ordered:
        family = item["family"]
        if family_counts[family] >= int(ranking["family_survivor_cap"]):
            continue
        selected.append(item)
        family_counts[family] += 1
        if len(selected) >= int(ranking["overall_survivor_cap"]):
            break
    return selected, [item["trial_id"] for item in frontier]


def _write_result(root: Path, record: Mapping[str, object]) -> dict[str, str]:
    payload = _canonical_json(record)
    digest = _sha256(payload)
    directory = root / "historical-strategy-search" / "hsse-003"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"survivor-ranking-{digest[:24]}.json"
    if path.exists():
        if path.read_bytes() != payload:
            raise HSSESurvivorError("existing HSSE-003 result differs")
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    return {
        "artifact_relative_path": path.relative_to(root).as_posix(),
        "artifact_file_sha256": digest,
    }


def run_ranking(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
    protocol_path: Path = DEFAULT_PROTOCOL_PATH,
) -> dict[str, object]:
    protocol, protocol_sha = validate_protocol(protocol_path)
    ledgers, search_index = _load_search_artifacts(runtime_root, protocol)
    precheck = []
    for family in hsse2.FAMILIES:
        for record in ledgers[family].values():
            if (
                record["development_filter_precheck"]["status"]
                == "ELIGIBLE_FOR_HSSE003_RECOMPUTE"
            ):
                precheck.append(record)
    precheck.sort(
        key=lambda x: (
            hsse2.FAMILIES.index(x["family"]),
            x["parameters"]["n1"],
            x["parameters"]["n2"],
        )
    )
    if len(precheck) != protocol["exact_recompute"]["expected_candidate_count"]:
        raise HSSESurvivorError("HSSE-003 candidate count differs from registration")

    try:
        root = replay._safe_root(runtime_root)
        corpus = controls._load_control_corpus(
            runtime_root=root,
            quality_manifest_relative_path=quality_manifest_relative_path,
            quality_manifest_file_sha256=quality_manifest_file_sha256,
        )
    except (replay.ReplayError, controls.ControlError) as exc:
        raise HSSESurvivorError(str(exc)) from None
    if corpus.event_id != "CRL-CONTROL-DEV-POOL-001":
        raise HSSESurvivorError("HSSE-003 loaded the wrong corpus")
    if quality_manifest_file_sha256 != search_index["quality_manifest_file_sha256"]:
        raise HSSESurvivorError("HSSE-003 quality manifest differs from HSSE-002")

    signal_series = {
        symbol: hsse2._series_for_symbol(corpus, symbol)
        for symbol in ("BTCUSDT", "ETHUSDT")
    }
    exact_series = {
        symbol: _exact_series(corpus, symbol)
        for symbol in ("BTCUSDT", "ETHUSDT")
    }
    hsse1_protocol, _, context = hsse2.load_plan()
    folds = context["protocol"]["development_cross_validation"]["folds"]
    signal_cache: dict[tuple[str, str, int], object] = {}
    exact_results = []
    for search_record in precheck:
        exact = _exact_candidate(
            search_record=search_record,
            corpus=corpus,
            folds=folds,
            exact_policy=protocol["exact_recompute"],
            gate=protocol["exact_gate"],
            signal_cache=signal_cache,
            signal_series=signal_series,
            exact_series=exact_series,
        )
        p = exact["parameters"]
        exact["neighbor_robustness"] = _neighbor_evidence(
            exact["family"],
            p["n1"],
            p["n2"],
            ledgers[exact["family"]],
            protocol["neighbor_robustness"],
        )
        exact_results.append(exact)

    selected, frontier_ids = _rank(exact_results, protocol["ranking"])
    proposed = [
        {
            "proposal_rank": index + 1,
            "trial_id": item["trial_id"],
            "family": item["family"],
            "parameters": item["parameters"],
            "search_trial_sha256": item["search_trial_sha256"],
            "exact_metrics": {
                "completed_trades": item["completed_trades"],
                "total_net_pnl_after_costs_quote": item["base"][
                    "total_net_pnl_after_costs_quote"
                ],
                "expectancy_quote": item["base"]["expectancy_quote"],
                "profit_factor": item["base"]["profit_factor"],
                "profit_factor_infinite": item["base"]["profit_factor_infinite"],
                "positive_development_cell_fraction": item["base"][
                    "positive_development_cell_fraction"
                ],
                "maximum_drawdown_fraction": item["base"][
                    "maximum_drawdown_fraction"
                ],
                "stress_total_net_pnl_after_costs_quote": item["stress"][
                    "total_net_pnl_after_costs_quote"
                ],
                "neighbor_pass_fraction": item["neighbor_robustness"][
                    "neighbor_pass_fraction"
                ],
            },
        }
        for index, item in enumerate(selected)
    ]

    result = {
        "schema": "YATL_HSSE_SURVIVOR_RANKING_RESULT",
        "schema_version": SCHEMA_VERSION,
        "implementation_id": IMPLEMENTATION_ID,
        "protocol_sha256": protocol_sha,
        "source_search_result_sha256": protocol["input_search"]["result_sha256"],
        "quality_manifest_relative_path": quality_manifest_relative_path,
        "quality_manifest_file_sha256": quality_manifest_file_sha256,
        "source_corpus_id": corpus.event_id,
        "input_total_trial_count": protocol["input_search"]["total_trial_count"],
        "input_precheck_candidate_count": len(precheck),
        "exact_gate_pass_count": sum(
            item["exact_gate"]["status"] == "PASS" for item in exact_results
        ),
        "neighbor_robustness_pass_count": sum(
            item["exact_gate"]["status"] == "PASS"
            and item["neighbor_robustness"]["status"] == "PASS"
            for item in exact_results
        ),
        "pareto_front_trial_ids": frontier_ids,
        "proposed_survivor_count": len(proposed),
        "proposed_survivors": proposed,
        "all_exact_recomputations": exact_results,
        "ranking_performed": True,
        "survivor_freeze_performed": False,
        "blind_oos_read": False,
        "audit_holdout_read": False,
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
        "p11_locked": True,
    }
    result["result_sha256"] = _sha256(_canonical_json(result))
    artifact = _write_result(root, result)
    return {
        "implementation_id": IMPLEMENTATION_ID,
        "protocol_sha256": protocol_sha,
        "input_total_trial_count": result["input_total_trial_count"],
        "input_precheck_candidate_count": result["input_precheck_candidate_count"],
        "exact_gate_pass_count": result["exact_gate_pass_count"],
        "neighbor_robustness_pass_count": result[
            "neighbor_robustness_pass_count"
        ],
        "pareto_front_trial_ids": frontier_ids,
        "proposed_survivor_count": len(proposed),
        "proposed_survivors": proposed,
        **artifact,
        "result_sha256": result["result_sha256"],
        "ranking_performed": True,
        "survivor_freeze_performed": False,
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
        prog="python -m research.historical_strategy_search.survivor_ranking",
        description="HSSE-003 exact Development recomputation and ranking",
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--quality-manifest", required=True)
    parser.add_argument("--quality-manifest-sha256", required=True)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)
    parser.add_argument("--validate-protocol-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.validate_protocol_only:
        protocol, digest = validate_protocol(args.protocol)
        result = {
            "implementation_id": IMPLEMENTATION_ID,
            "protocol_id": protocol["protocol_id"],
            "protocol_sha256": digest,
            "expected_candidate_count": protocol["exact_recompute"][
                "expected_candidate_count"
            ],
            "input_total_trial_count": protocol["input_search"][
                "total_trial_count"
            ],
            "research_only": True,
            "p10_write_allowed": False,
            "p11_locked": True,
        }
    else:
        result = run_ranking(
            runtime_root=args.runtime_root,
            quality_manifest_relative_path=args.quality_manifest,
            quality_manifest_file_sha256=args.quality_manifest_sha256,
            protocol_path=args.protocol,
        )
    print(_json(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HSSESurvivorError as exc:
        print(
            _json(
                {
                    "code": "HSSE003_SURVIVOR_ERROR",
                    "reason": str(exc),
                    "research_only": True,
                    "p10_write_allowed": False,
                    "p11_locked": True,
                }
            )
        )
        raise SystemExit(2)
