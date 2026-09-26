"""RIE-003 reproduction-packet validation.

A reproduction packet binds an external research candidate to exact source and
implementation identities. It does not execute a strategy or promote evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Sequence


SCHEMA = "YATL_RESEARCH_REPRODUCTION_PACKET"
SCHEMA_VERSION = "0.1.0"
MAX_PACKET_BYTES = 512 * 1024
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
CANDIDATE_RE = re.compile(r"RIE-CAND-[0-9]{4}")
PACKET_RE = re.compile(r"RIE-RP-[0-9]{4}-V[0-9]+")
FREEZE_STATUSES = frozenset({"FROZEN", "PENDING_BYTES"})


class ReproductionPacketError(RuntimeError):
    """A reproduction packet violated the RIE-003 contract."""


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


def _exact(record: object, keys: Sequence[str]) -> bool:
    return isinstance(record, dict) and set(record) == set(keys)


def _text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 4096
    ):
        raise ReproductionPacketError(f"{label} is invalid")
    return value


def _https(value: object, label: str) -> str:
    value = _text(value, label)
    if not value.startswith("https://") or any(ch.isspace() for ch in value):
        raise ReproductionPacketError(f"{label} must be HTTPS")
    return value


def _string_list(value: object, label: str, *, required: bool = False) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) > 128
        or (required and not value)
    ):
        raise ReproductionPacketError(f"{label} list is invalid")
    result = [_text(item, label) for item in value]
    if len(result) != len(set(result)):
        raise ReproductionPacketError(f"{label} contains duplicates")
    return result


def validate_packet(path: Path) -> dict[str, object]:
    if not isinstance(path, Path):
        raise ReproductionPacketError("packet path must be a Path")
    target = path.expanduser()
    if target.exists() and target.is_symlink():
        raise ReproductionPacketError("symlink packet is forbidden")
    try:
        payload = target.read_bytes()
    except OSError:
        raise ReproductionPacketError("cannot read reproduction packet") from None
    if not payload or len(payload) > MAX_PACKET_BYTES:
        raise ReproductionPacketError("packet size is invalid")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ReproductionPacketError("packet is not UTF-8 JSON") from None

    top = (
        "schema",
        "schema_version",
        "packet_id",
        "candidate_id",
        "source_binding",
        "implementation_binding",
        "source_method",
        "yatl_adaptation",
        "train_search",
        "unresolved",
        "readiness",
        "research_only",
        "p10_read",
        "p10_write_allowed",
        "p10_evidence_effect",
        "strategy_evidence_effect",
        "trade_permission",
        "order_endpoint",
        "quantity_authority",
        "risk_authorization_mutation",
        "ai_direct_execution",
        "p11_locked",
    )
    if not _exact(record, top):
        raise ReproductionPacketError("top-level packet schema is invalid")
    if (
        record["schema"] != SCHEMA
        or record["schema_version"] != SCHEMA_VERSION
        or not isinstance(record["packet_id"], str)
        or PACKET_RE.fullmatch(record["packet_id"]) is None
        or not isinstance(record["candidate_id"], str)
        or CANDIDATE_RE.fullmatch(record["candidate_id"]) is None
    ):
        raise ReproductionPacketError("packet identity is invalid")

    source = record["source_binding"]
    if not _exact(
        source,
        (
            "uri",
            "immutable_identity",
            "freeze_status",
            "content_sha256",
        ),
    ):
        raise ReproductionPacketError("source binding schema is invalid")
    _https(source["uri"], "source uri")
    _text(source["immutable_identity"], "immutable source identity")
    if source["freeze_status"] not in FREEZE_STATUSES:
        raise ReproductionPacketError("source freeze status is invalid")
    source_sha = source["content_sha256"]
    if source["freeze_status"] == "FROZEN":
        if not isinstance(source_sha, str) or SHA256_RE.fullmatch(source_sha) is None:
            raise ReproductionPacketError("frozen source requires SHA-256")
    elif source_sha is not None:
        raise ReproductionPacketError(
            "pending source bytes cannot claim a content SHA-256"
        )

    impl = record["implementation_binding"]
    if not _exact(
        impl,
        (
            "repository",
            "repository_uri",
            "commit_sha",
            "license",
            "files",
            "snapshot_sha256",
        ),
    ):
        raise ReproductionPacketError("implementation binding schema is invalid")
    _text(impl["repository"], "repository")
    _https(impl["repository_uri"], "repository uri")
    if (
        not isinstance(impl["commit_sha"], str)
        or GIT_SHA_RE.fullmatch(impl["commit_sha"]) is None
    ):
        raise ReproductionPacketError("implementation commit SHA is invalid")
    _text(impl["license"], "implementation license")
    if not isinstance(impl["files"], list) or not impl["files"]:
        raise ReproductionPacketError("implementation file binding is missing")
    seen_paths = set()
    for item in impl["files"]:
        if not _exact(item, ("path", "blob_sha")):
            raise ReproductionPacketError("implementation file schema is invalid")
        file_path = _text(item["path"], "implementation path")
        if file_path in seen_paths:
            raise ReproductionPacketError("duplicate implementation path")
        seen_paths.add(file_path)
        if (
            not isinstance(item["blob_sha"], str)
            or GIT_SHA_RE.fullmatch(item["blob_sha"]) is None
        ):
            raise ReproductionPacketError("implementation blob SHA is invalid")
    snapshot_sha = impl["snapshot_sha256"]
    if not isinstance(snapshot_sha, str) or SHA256_RE.fullmatch(snapshot_sha) is None:
        raise ReproductionPacketError("implementation snapshot SHA-256 is invalid")
    snapshot = {
        "schema": "YATL_EXTERNAL_REPOSITORY_SNAPSHOT",
        "schema_version": "0.1.0",
        "repository": impl["repository"],
        "commit_sha": impl["commit_sha"],
        "files": impl["files"],
    }
    calculated_snapshot_sha = _sha256(
        (_json(snapshot) + "\n").encode("utf-8")
    )
    if calculated_snapshot_sha != snapshot_sha:
        raise ReproductionPacketError(
            "implementation snapshot SHA-256 does not match bound files"
        )

    method = record["source_method"]
    if not _exact(
        method,
        (
            "market_data",
            "signal_families",
            "paper_parameter_domain",
            "observed_code_grid",
            "entry_rule",
            "exit_rule",
            "optimization_objective",
            "walk_forward",
            "source_cost_model",
            "source_gap_handling",
            "paper_code_discrepancies",
        ),
    ):
        raise ReproductionPacketError("source method schema is invalid")
    _text(method["market_data"], "market data")
    _string_list(method["signal_families"], "signal families", required=True)
    _text(method["paper_parameter_domain"], "paper parameter domain")
    _text(method["observed_code_grid"], "observed code grid")
    _text(method["entry_rule"], "entry rule")
    _text(method["exit_rule"], "exit rule")
    _text(method["optimization_objective"], "optimization objective")
    _text(method["walk_forward"], "walk forward")
    _text(method["source_cost_model"], "source cost model")
    _text(method["source_gap_handling"], "source gap handling")
    _string_list(
        method["paper_code_discrepancies"],
        "paper/code discrepancies",
        required=True,
    )

    adaptation = record["yatl_adaptation"]
    if not _exact(
        adaptation,
        (
            "mode",
            "symbols",
            "timeframe",
            "entry_rule",
            "exit_rule",
            "fee_bps",
            "adverse_slippage_bps",
            "execution",
            "gap_handling",
            "source_fidelity",
        ),
    ):
        raise ReproductionPacketError("YATL adaptation schema is invalid")
    if adaptation["mode"] != "LONG_ONLY_SPOT_RESEARCH":
        raise ReproductionPacketError("YATL adaptation must remain long-only Spot")
    _string_list(adaptation["symbols"], "adaptation symbols", required=True)
    _text(adaptation["timeframe"], "adaptation timeframe")
    _text(adaptation["entry_rule"], "adaptation entry rule")
    _text(adaptation["exit_rule"], "adaptation exit rule")
    for key in ("fee_bps", "adverse_slippage_bps"):
        value = adaptation[key]
        if type(value) is not int or value < 0 or value > 1000:
            raise ReproductionPacketError(f"{key} is invalid")
    _text(adaptation["execution"], "adaptation execution")
    _text(adaptation["gap_handling"], "adaptation gap handling")
    _text(adaptation["source_fidelity"], "source fidelity")

    search = record["train_search"]
    if not _exact(
        search,
        (
            "status",
            "families",
            "parameter_grid",
            "selection_scope",
            "multiple_testing_accounted",
            "oos_used_for_selection",
        ),
    ):
        raise ReproductionPacketError("train search schema is invalid")
    if search["status"] not in {"PLANNED", "FROZEN"}:
        raise ReproductionPacketError("train search status is invalid")
    _string_list(search["families"], "search families", required=True)
    _text(search["parameter_grid"], "parameter grid")
    _text(search["selection_scope"], "selection scope")
    if search["multiple_testing_accounted"] is not True:
        raise ReproductionPacketError("multiple testing must be accounted for")
    if search["oos_used_for_selection"] is not False:
        raise ReproductionPacketError("OOS cannot be used for train selection")

    _string_list(record["unresolved"], "unresolved", required=True)

    readiness = record["readiness"]
    if not _exact(
        readiness,
        (
            "candidate_status",
            "implementation_frozen",
            "source_bytes_frozen",
            "readiness_basis",
            "ready_for_train_search",
            "blockers",
        ),
    ):
        raise ReproductionPacketError("readiness schema is invalid")
    if readiness["candidate_status"] not in {
        "NEW",
        "REPRODUCIBLE",
        "READY_FOR_TRAIN_SEARCH",
    }:
        raise ReproductionPacketError("candidate readiness status is invalid")
    if type(readiness["implementation_frozen"]) is not bool:
        raise ReproductionPacketError("implementation_frozen must be boolean")
    if type(readiness["source_bytes_frozen"]) is not bool:
        raise ReproductionPacketError("source_bytes_frozen must be boolean")
    if type(readiness["ready_for_train_search"]) is not bool:
        raise ReproductionPacketError("ready_for_train_search must be boolean")
    if readiness["readiness_basis"] not in {
        "FROZEN_SOURCE",
        "FROZEN_IMPLEMENTATION",
        "NOT_READY",
    }:
        raise ReproductionPacketError("readiness basis is invalid")
    blockers = _string_list(readiness["blockers"], "readiness blockers")
    if source["freeze_status"] == "PENDING_BYTES":
        if readiness["source_bytes_frozen"] is not False:
            raise ReproductionPacketError("pending source bytes must remain unfrozen")
        if readiness["ready_for_train_search"] is True:
            if (
                readiness["readiness_basis"] != "FROZEN_IMPLEMENTATION"
                or readiness["implementation_frozen"] is not True
                or search["status"] != "FROZEN"
                or readiness["candidate_status"] != "READY_FOR_TRAIN_SEARCH"
                or blockers
            ):
                raise ReproductionPacketError(
                    "implementation-based readiness is not fully frozen"
                )
        elif not blockers:
            raise ReproductionPacketError(
                "pending non-ready source requires a readiness blocker"
            )
    if readiness["candidate_status"] == "READY_FOR_TRAIN_SEARCH" and (
        readiness["ready_for_train_search"] is not True
    ):
        raise ReproductionPacketError(
            "READY_FOR_TRAIN_SEARCH status requires ready_for_train_search"
        )

    safety = (
        record["research_only"] is True
        and record["p10_read"] is False
        and record["p10_write_allowed"] is False
        and record["p10_evidence_effect"] == "NONE"
        and record["strategy_evidence_effect"] == "NONE"
        and record["trade_permission"] is False
        and record["order_endpoint"] is False
        and record["quantity_authority"] is False
        and record["risk_authorization_mutation"] is False
        and record["ai_direct_execution"] is False
        and record["p11_locked"] is True
    )
    if not safety:
        raise ReproductionPacketError("reproduction safety invariants are invalid")

    return {
        "schema": "YATL_RESEARCH_REPRODUCTION_PACKET_VALIDATION",
        "schema_version": SCHEMA_VERSION,
        "packet_id": record["packet_id"],
        "candidate_id": record["candidate_id"],
        "packet_file_sha256": _sha256(payload),
        "source_freeze_status": source["freeze_status"],
        "implementation_commit_sha": impl["commit_sha"],
        "implementation_file_count": len(impl["files"]),
        "candidate_status": readiness["candidate_status"],
        "ready_for_train_search": readiness["ready_for_train_search"],
        "network_used": False,
        "strategy_evidence_effect": "NONE",
        "research_only": True,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "p11_locked": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research.research_intake.reproduction",
        description="Validate an RIE-003 reproduction packet",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--packet", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "validate":
        raise ReproductionPacketError("unsupported reproduction command")
    print(_json(validate_packet(args.packet)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReproductionPacketError as exc:
        print(
            _json(
                {
                    "code": "RIE003_REPRODUCTION_PACKET_ERROR",
                    "reason": str(exc),
                    "research_only": True,
                    "p10_write_allowed": False,
                    "p11_locked": True,
                }
            )
        )
        raise SystemExit(2)
