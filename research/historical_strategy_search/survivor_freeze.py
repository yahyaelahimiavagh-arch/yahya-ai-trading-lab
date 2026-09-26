"""HSSE-004A immutable survivor-freeze validation.

This module freezes the exact HSSE-003 proposed survivor set before any Blind
OOS acquisition or outcome access. It performs no network access and no replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence


SCHEMA = "YATL_HSSE_SURVIVOR_FREEZE"
SCHEMA_VERSION = "0.1.0"
FREEZE_ID = "HSSE-004A-SURVIVOR-FREEZE-001"
MAX_FREEZE_BYTES = 2 * 1024 * 1024
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class HSSEFreezeError(RuntimeError):
    """HSSE-004A survivor freeze is invalid."""


def _json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, str):
        raise HSSEFreezeError(f"{label} must be a decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise HSSEFreezeError(f"{label} is invalid") from None
    if not number.is_finite():
        raise HSSEFreezeError(f"{label} is not finite")
    return number


def validate_freeze(path: Path) -> dict[str, object]:
    if path.is_symlink():
        raise HSSEFreezeError("symlink freeze is forbidden")
    try:
        payload = path.read_bytes()
    except OSError:
        raise HSSEFreezeError("cannot read HSSE-004A freeze") from None
    if not payload or len(payload) > MAX_FREEZE_BYTES:
        raise HSSEFreezeError("HSSE-004A freeze size is invalid")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HSSEFreezeError("HSSE-004A freeze is not UTF-8 JSON") from None
    if not isinstance(record, dict):
        raise HSSEFreezeError("HSSE-004A freeze must be an object")

    if (
        record.get("schema") != SCHEMA
        or record.get("schema_version") != SCHEMA_VERSION
        or record.get("freeze_id") != FREEZE_ID
        or record.get("status") != "FROZEN_BEFORE_BLIND_OOS_DATA_ACCESS"
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
        raise HSSEFreezeError("HSSE-004A safety invariants are invalid")

    source = record.get("source_hsse003")
    if not isinstance(source, dict):
        raise HSSEFreezeError("HSSE-003 source binding is missing")
    for key in (
        "protocol_sha256",
        "artifact_file_sha256",
        "result_sha256",
    ):
        if (
            not isinstance(source.get(key), str)
            or SHA256_RE.fullmatch(source[key]) is None
        ):
            raise HSSEFreezeError(f"HSSE-003 {key} is invalid")
    if (
        source.get("implementation_id") != "HSSE-003-SURVIVOR-RANKING/0.1.0"
        or source.get("final_head_sha")
        != "7f7097c076816bf2b4eacc6ca95597e54afb0995"
        or source.get("input_precheck_candidate_count") != 16
        or source.get("exact_gate_pass_count") != 15
        or source.get("neighbor_robustness_pass_count") != 14
        or source.get("proposed_survivor_count") != 6
        or source.get("survivor_freeze_performed") is not False
        or source.get("blind_oos_read") is not False
        or source.get("audit_holdout_read") is not False
    ):
        raise HSSEFreezeError("HSSE-003 source outcome binding is invalid")

    survivors = record.get("survivors")
    if not isinstance(survivors, list) or len(survivors) != 6:
        raise HSSEFreezeError("HSSE-004A requires exactly six frozen survivors")
    expected = [
        ("HSSE004A-SURV-001", "TREND_MA_EMA", 11, 511),
        ("HSSE004A-SURV-002", "TREND_MA_EMA", 11, 491),
        ("HSSE004A-SURV-003", "TREND_MA_EMA", 11, 471),
        ("HSSE004A-SURV-004", "TREND_MA_DEMA", 121, 131),
        ("HSSE004A-SURV-005", "TREND_MA_DEMA", 91, 191),
        ("HSSE004A-SURV-006", "TREND_MA_DEMA", 111, 161),
    ]
    seen_ids = set()
    seen_trials = set()
    for item, identity in zip(survivors, expected):
        if not isinstance(item, dict):
            raise HSSEFreezeError("frozen survivor is invalid")
        frozen_id, family, n1, n2 = identity
        params = item.get("parameters")
        metrics = item.get("development_reference")
        if (
            item.get("frozen_id") != frozen_id
            or item.get("family") != family
            or not isinstance(params, dict)
            or params.get("n1") != n1
            or params.get("n2") != n2
            or not isinstance(item.get("source_trial_id"), str)
            or not isinstance(item.get("search_trial_sha256"), str)
            or SHA256_RE.fullmatch(item["search_trial_sha256"]) is None
            or not isinstance(metrics, dict)
        ):
            raise HSSEFreezeError("frozen survivor identity differs")
        if item["frozen_id"] in seen_ids or item["source_trial_id"] in seen_trials:
            raise HSSEFreezeError("duplicate frozen survivor")
        seen_ids.add(item["frozen_id"])
        seen_trials.add(item["source_trial_id"])
        for metric in (
            "expectancy_quote",
            "profit_factor",
            "positive_development_cell_fraction",
            "maximum_drawdown_fraction",
            "total_net_pnl_after_costs_quote",
            "stress_total_net_pnl_after_costs_quote",
            "neighbor_pass_fraction",
        ):
            _decimal(metrics.get(metric), f"{frozen_id} {metric}")
        if int(metrics.get("completed_trades", -1)) <= 0:
            raise HSSEFreezeError("frozen survivor trade count is invalid")

    rules = record.get("freeze_rules")
    if (
        not isinstance(rules, dict)
        or rules.get("survivor_count") != 6
        or rules.get("family_counts")
        != {"TREND_MA_EMA": 3, "TREND_MA_DEMA": 3}
        or any(
            rules.get(key) is not False
            for key in (
                "parameters_mutable_after_freeze",
                "family_mutable_after_freeze",
                "signal_semantics_mutable_after_freeze",
                "execution_semantics_mutable_after_freeze",
                "cost_model_mutable_after_freeze",
                "quantity_mutable_after_freeze",
                "survivor_set_mutable_after_freeze",
                "blind_failure_retune_same_holdout",
                "development_reranking_after_blind_outcome",
            )
        )
    ):
        raise HSSEFreezeError("HSSE-004A freeze mutation rules are invalid")

    execution = record.get("frozen_signal_and_execution")
    if (
        not isinstance(execution, dict)
        or execution.get("timeframe") != "1h"
        or execution.get("side") != "LONG_ONLY_SPOT"
        or execution.get("quantity") != "0.001"
        or execution.get("initial_equity_quote") != "10000"
        or execution.get("base_fee_bps") != "10"
        or execution.get("base_adverse_slippage_bps") != "5"
        or execution.get("stress_fee_bps") != "20"
        or execution.get("stress_adverse_slippage_bps") != "10"
        or execution.get("exact_economic_arithmetic") != "DECIMAL_256"
        or execution.get("gap_policy") != "NEVER_INTERPOLATE_OR_FORWARD_FILL"
    ):
        raise HSSEFreezeError("HSSE-004A frozen execution contract is invalid")

    blind = record.get("blind_oos")
    gate = record.get("blind_gate")
    if (
        not isinstance(blind, dict)
        or blind.get("corpus_id") != "HSSE-BLIND-OOS-001"
        or blind.get("acquisition_start_utc") != "2022-11-01T00:00:00Z"
        or blind.get("analysis_start_utc") != "2023-01-01T00:00:00Z"
        or blind.get("analysis_end_exclusive_utc") != "2025-01-01T00:00:00Z"
        or blind.get("symbols") != ["BTCUSDT", "ETHUSDT"]
        or blind.get("intervals") != ["15m", "1h", "4h"]
        or blind.get("state_before_hsse004b") != "SEALED_UNACQUIRED_BY_HSSE"
        or blind.get("outcome_access_before_hsse004b") is not False
        or blind.get("reuse_for_retuning_after_first_outcome") is not False
        or blind.get("execution_count_per_frozen_survivor") != 1
        or not isinstance(gate, dict)
        or gate.get("minimum_completed_trades_total") != 40
        or gate.get("minimum_completed_trades_per_symbol") != 10
        or gate.get("minimum_profit_factor_after_base_costs") != "1.05"
        or gate.get("minimum_positive_calendar_quarter_fraction") != "0.50"
        or gate.get("maximum_drawdown_fraction") != "0.12"
        or gate.get("failure_policy")
        != "RETAIN_FAILURE; DO_NOT_RETUNE_ON_THIS_HOLDOUT"
    ):
        raise HSSEFreezeError("HSSE-004A blind OOS contract is invalid")

    return {
        "schema": "YATL_HSSE_SURVIVOR_FREEZE_VALIDATION",
        "schema_version": SCHEMA_VERSION,
        "freeze_id": FREEZE_ID,
        "freeze_file_sha256": _sha256(payload),
        "source_hsse003_result_sha256": source["result_sha256"],
        "survivor_count": len(survivors),
        "families": {
            "TREND_MA_EMA": 3,
            "TREND_MA_DEMA": 3,
        },
        "blind_oos_start_utc": blind["analysis_start_utc"],
        "blind_oos_end_exclusive_utc": blind["analysis_end_exclusive_utc"],
        "blind_oos_accessed": False,
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research.historical_strategy_search.survivor_freeze",
        description="Validate HSSE-004A frozen survivors before Blind OOS",
    )
    parser.add_argument("--freeze", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(_json(validate_freeze(args.freeze)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HSSEFreezeError as exc:
        print(
            _json(
                {
                    "code": "HSSE004A_FREEZE_ERROR",
                    "reason": str(exc),
                    "research_only": True,
                    "p10_write_allowed": False,
                    "p11_locked": True,
                }
            )
        )
        raise SystemExit(2)
