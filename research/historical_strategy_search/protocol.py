"""HSSE-001 protocol validator.

This module validates data isolation, search budgets and evidence boundaries.
It performs no strategy search and has no network or execution authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


SCHEMA = "YATL_HSSE_SEARCH_PROTOCOL"
SCHEMA_VERSION = "0.1.0"
PROTOCOL_ID = "HSSE-001-SEARCH-PROTOCOL"
MAX_PROTOCOL_BYTES = 1024 * 1024


class HSSEProtocolError(RuntimeError):
    """HSSE protocol violated a frozen research boundary."""


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


def _time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise HSSEProtocolError(f"{label} must be UTC Z time")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise HSSEProtocolError(f"{label} is invalid") from None
    if parsed.tzinfo != timezone.utc:
        raise HSSEProtocolError(f"{label} is not UTC")
    return parsed


def load_protocol(path: Path) -> tuple[dict[str, object], str]:
    if not isinstance(path, Path):
        raise HSSEProtocolError("protocol path must be a Path")
    target = path.expanduser()
    if target.exists() and target.is_symlink():
        raise HSSEProtocolError("symlink protocol is forbidden")
    try:
        payload = target.read_bytes()
    except OSError:
        raise HSSEProtocolError("cannot read HSSE protocol") from None
    if not payload or len(payload) > MAX_PROTOCOL_BYTES:
        raise HSSEProtocolError("HSSE protocol size is invalid")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HSSEProtocolError("HSSE protocol is not UTF-8 JSON") from None
    if not isinstance(record, dict):
        raise HSSEProtocolError("HSSE protocol must be an object")
    return record, _sha256(payload)


def validate_protocol(path: Path) -> dict[str, object]:
    record, digest = load_protocol(path)
    if (
        record.get("schema") != SCHEMA
        or record.get("schema_version") != SCHEMA_VERSION
        or record.get("protocol_id") != PROTOCOL_ID
        or record.get("status") != "REGISTERED_BEFORE_HSSE_SEARCH_OUTCOMES"
        or record.get("research_only") is not True
        or record.get("paper_only") is not True
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
        raise HSSEProtocolError("HSSE safety invariants are invalid")

    boundaries = record.get("data_boundaries")
    if not isinstance(boundaries, dict):
        raise HSSEProtocolError("data boundaries are missing")
    dev = boundaries.get("development")
    blind = boundaries.get("blind_oos")
    audit = boundaries.get("final_audit_holdout")
    reserve = boundaries.get("recent_reserve")
    if not all(isinstance(x, dict) for x in (dev, blind, audit, reserve)):
        raise HSSEProtocolError("HSSE boundary records are invalid")

    dev_start = _time(dev.get("analysis_start_utc"), "development start")
    dev_end = _time(dev.get("analysis_end_exclusive_utc"), "development end")
    blind_start = _time(blind.get("analysis_start_utc"), "blind start")
    blind_end = _time(blind.get("analysis_end_exclusive_utc"), "blind end")
    audit_start = _time(audit.get("analysis_start_utc"), "audit start")
    audit_end = _time(audit.get("analysis_end_exclusive_utc"), "audit end")
    reserve_start = _time(reserve.get("start_utc"), "reserve start")

    if not (
        dev_start < dev_end == blind_start < blind_end
        and blind_end == audit_start < audit_end == reserve_start
    ):
        raise HSSEProtocolError("development/blind/audit/reserve boundaries overlap or gap")

    if dev.get("corpus_id") != "CRL-CONTROL-DEV-POOL-001":
        raise HSSEProtocolError("development corpus identity changed")
    if blind.get("inspection_status") != "SEALED_UNTIL_HSSE-004":
        raise HSSEProtocolError("blind OOS is not sealed")
    if audit.get("inspection_status") != "SEALED_UNTIL_HSSE-006":
        raise HSSEProtocolError("audit holdout is not sealed")

    search = record.get("search_budget")
    if not isinstance(search, dict):
        raise HSSEProtocolError("search budget is missing")
    per_family = search.get("maximum_trials_per_family")
    families = search.get("maximum_eligible_families")
    total = search.get("maximum_total_trials")
    if (
        type(per_family) is not int
        or type(families) is not int
        or type(total) is not int
        or not 1 <= families <= 16
        or not 1 <= per_family <= 10000
        or not 1 <= total <= 50000
        or total > per_family * families
        or search.get("all_trials_count_toward_multiple_testing") is not True
        or search.get("failed_trials_retained") is not True
        or search.get("hidden_retries_forbidden") is not True
        or search.get("budget_may_not_be_increased_after_viewing_results") is not True
    ):
        raise HSSEProtocolError("search budget invariants are invalid")

    execution = record.get("execution_semantics")
    if (
        not isinstance(execution, dict)
        or execution.get("fixed_research_quantity") != "0.001"
        or execution.get("fee_bps") != 10
        or execution.get("adverse_slippage_bps") != 5
        or execution.get("execution") != "NEXT_PRIMARY_OPEN_LONG_ONLY_SPOT"
        or execution.get("shorting") is not False
        or execution.get("futures") is not False
        or execution.get("leverage") is not False
    ):
        raise HSSEProtocolError("HSSE execution semantics are invalid")

    ranking = record.get("ranking")
    if (
        not isinstance(ranking, dict)
        or ranking.get("raw_pnl_only_ranking_forbidden") is not True
        or ranking.get("method") != "PARETO_THEN_LEXICOGRAPHIC"
        or not 1 <= ranking.get("family_survivor_cap", 0) <= 5
        or not 1 <= ranking.get("overall_survivor_cap", 0) <= 20
        or ranking.get("survivor_count_is_a_cap_not_a_quota") is not True
    ):
        raise HSSEProtocolError("HSSE ranking invariants are invalid")

    freeze = record.get("freeze_before_blind_oos")
    if (
        not isinstance(freeze, dict)
        or freeze.get("required") is not True
        or freeze.get("post_freeze_parameter_change") != "FORBIDDEN"
        or freeze.get("post_blind_failure_retune_same_holdout") != "FORBIDDEN"
    ):
        raise HSSEProtocolError("HSSE freeze invariants are invalid")

    anti = record.get("anti_overfitting")
    if (
        not isinstance(anti, dict)
        or anti.get("development_outcomes_may_inform_selection") is not True
        or anti.get("blind_oos_outcomes_may_inform_selection") is not False
        or anti.get("audit_holdout_outcomes_may_inform_selection") is not False
        or anti.get("candidate_deduplication_required") is not True
        or anti.get("trial_ledger_required") is not True
        or anti.get("negative_results_retained") is not True
        or anti.get("no_edge_found_is_valid_outcome") is not True
    ):
        raise HSSEProtocolError("HSSE anti-overfitting invariants are invalid")

    folds = record.get("development_cross_validation", {}).get("folds")
    if not isinstance(folds, list) or len(folds) != 5:
        raise HSSEProtocolError("development folds are invalid")
    previous_eval_end = None
    for index, fold in enumerate(folds, 1):
        if not isinstance(fold, dict) or fold.get("fold_id") != f"HSSE-D{index:03d}":
            raise HSSEProtocolError("development fold identity is invalid")
        train_start = _time(fold.get("training_start_utc"), "fold train start")
        train_end = _time(fold.get("training_end_exclusive_utc"), "fold train end")
        eval_start = _time(fold.get("evaluation_start_utc"), "fold eval start")
        eval_end = _time(fold.get("evaluation_end_exclusive_utc"), "fold eval end")
        if not train_start == dev_start or not train_start < train_end == eval_start < eval_end:
            raise HSSEProtocolError("development fold chronology is invalid")
        if previous_eval_end is not None and previous_eval_end != eval_start:
            raise HSSEProtocolError("development folds are not sequential")
        if eval_end > dev_end:
            raise HSSEProtocolError("development fold leaks past development boundary")
        previous_eval_end = eval_end

    return {
        "schema": "YATL_HSSE_SEARCH_PROTOCOL_VALIDATION",
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_file_sha256": digest,
        "development_end_exclusive_utc": dev["analysis_end_exclusive_utc"],
        "blind_oos_start_utc": blind["analysis_start_utc"],
        "blind_oos_end_exclusive_utc": blind["analysis_end_exclusive_utc"],
        "audit_start_utc": audit["analysis_start_utc"],
        "audit_end_exclusive_utc": audit["analysis_end_exclusive_utc"],
        "maximum_total_trials": total,
        "maximum_survivors": ranking["overall_survivor_cap"],
        "blind_oos_sealed": True,
        "audit_holdout_sealed": True,
        "network_used": False,
        "research_only": True,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "p11_locked": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research.historical_strategy_search.protocol",
        description="Validate the frozen HSSE-001 search protocol",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--protocol", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "validate":
        raise HSSEProtocolError("unsupported HSSE command")
    print(_json(validate_protocol(args.protocol)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HSSEProtocolError as exc:
        print(
            _json(
                {
                    "code": "HSSE001_PROTOCOL_ERROR",
                    "reason": str(exc),
                    "research_only": True,
                    "p10_write_allowed": False,
                    "p11_locked": True,
                }
            )
        )
        raise SystemExit(2)
