"""RIE-001 deterministic research candidate registry.

The registry records external research hypotheses and provenance without trusting
reported performance or granting any strategy/execution authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA = "YATL_RESEARCH_CANDIDATE_REGISTRY"
SCHEMA_VERSION = "0.1.0"
REGISTRY_ID = "RIE-001-RESEARCH-CANDIDATES"
MAX_REGISTRY_BYTES = 4 * 1024 * 1024
MAX_CANDIDATES = 1000
MAX_LIST_ITEMS = 64
MAX_TEXT_CHARS = 4000

CANDIDATE_ID_RE = re.compile(r"RIE-CAND-[0-9]{4}")
SOURCE_ID_RE = re.compile(r"RIE-SRC-[0-9]{4}")

SOURCE_TIERS = frozenset({"A", "B", "C"})
SOURCE_TYPES = frozenset(
    {
        "PAPER",
        "REPOSITORY",
        "BOOK",
        "LECTURE",
        "TRANSCRIPT",
        "STRATEGY_LIBRARY",
        "OTHER",
    }
)
SOURCE_LANGUAGES = frozenset({"EN", "ZH", "MULTI", "OTHER"})
TECHNIQUE_FAMILIES = frozenset(
    {
        "TIME_SERIES_MOMENTUM",
        "VOLUME_WEIGHTED_MOMENTUM",
        "TREND",
        "BREAKOUT",
        "MEAN_REVERSION",
        "VOLATILITY",
        "REGIME_AWARE",
        "OTHER",
    }
)
STATUSES = frozenset(
    {
        "NEW",
        "DUPLICATE",
        "REPRODUCIBLE",
        "REJECTED_SOURCE",
        "READY_FOR_TRAIN_SEARCH",
    }
)
IMPLEMENTATION_AVAILABILITY = frozenset(
    {"NONE", "PSEUDOCODE", "CODE", "NOTEBOOK"}
)


class ResearchIntakeError(RuntimeError):
    """A research candidate registry violated the RIE contract."""


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


def _exact_keys(record: object, keys: Sequence[str]) -> bool:
    return isinstance(record, dict) and set(record) == set(keys)


def _text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ResearchIntakeError(f"{label} must be text")
    if value != value.strip():
        raise ResearchIntakeError(f"{label} must be trimmed")
    if not allow_empty and not value:
        raise ResearchIntakeError(f"{label} must not be empty")
    if len(value) > MAX_TEXT_CHARS:
        raise ResearchIntakeError(f"{label} is too long")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
        raise ResearchIntakeError(f"{label} contains control characters")
    return value


def _text_list(
    value: object,
    label: str,
    *,
    required: bool = False,
) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) > MAX_LIST_ITEMS
        or (required and not value)
    ):
        raise ResearchIntakeError(f"{label} list is invalid")
    result = [_text(item, label) for item in value]
    if len(set(result)) != len(result):
        raise ResearchIntakeError(f"{label} contains duplicates")
    return result


def _https_uri(value: object, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    uri = _text(value, label)
    if (
        not uri.startswith("https://")
        or any(ch.isspace() for ch in uri)
        or len(uri) > 2048
    ):
        raise ResearchIntakeError(f"{label} must be an HTTPS URI")
    return uri


def _date_or_none(value: object, label: str) -> str | None:
    if value is None:
        return None
    text = _text(value, label)
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text) is None:
        raise ResearchIntakeError(f"{label} must be YYYY-MM-DD or null")
    return text


def _normalized_rule(value: str) -> str:
    return " ".join(value.casefold().split())


def candidate_fingerprint(candidate: Mapping[str, object]) -> str:
    """Fingerprint strategy logic, deliberately excluding source/performance claims."""
    signature = {
        "technique_family": candidate["technique_family"],
        "market_universe": sorted(
            _normalized_rule(item) for item in candidate["market_universe"]
        ),
        "timeframes": sorted(
            _normalized_rule(item) for item in candidate["timeframes"]
        ),
        "hypothesis": _normalized_rule(str(candidate["hypothesis"])),
        "entry_rules": [
            _normalized_rule(item) for item in candidate["entry_rules"]
        ],
        "exit_rules": [
            _normalized_rule(item) for item in candidate["exit_rules"]
        ],
        "stop_rules": [
            _normalized_rule(item) for item in candidate["stop_rules"]
        ],
        "sizing_rules": [
            _normalized_rule(item) for item in candidate["sizing_rules"]
        ],
        "lookbacks": [
            _normalized_rule(item) for item in candidate["lookbacks"]
        ],
    }
    return _sha256(_canonical_json(signature))


def _validate_source(source: object) -> dict[str, object]:
    keys = (
        "source_id",
        "tier",
        "type",
        "language",
        "title",
        "uri",
        "publication_date",
        "authors",
        "provenance_notes",
    )
    if not _exact_keys(source, keys):
        raise ResearchIntakeError("candidate source schema is invalid")
    source_id = source["source_id"]
    if (
        not isinstance(source_id, str)
        or SOURCE_ID_RE.fullmatch(source_id) is None
    ):
        raise ResearchIntakeError("source identity is invalid")
    if source["tier"] not in SOURCE_TIERS:
        raise ResearchIntakeError("source tier is invalid")
    if source["type"] not in SOURCE_TYPES:
        raise ResearchIntakeError("source type is invalid")
    if source["language"] not in SOURCE_LANGUAGES:
        raise ResearchIntakeError("source language is invalid")
    _text(source["title"], "source title")
    _https_uri(source["uri"], "source uri")
    _date_or_none(source["publication_date"], "publication date")
    _text_list(source["authors"], "authors")
    _text_list(source["provenance_notes"], "provenance notes")
    return dict(source)


def _validate_reported_metric(record: object) -> dict[str, str]:
    keys = ("name", "value", "period", "caveat")
    if not _exact_keys(record, keys):
        raise ResearchIntakeError("reported metric schema is invalid")
    return {
        "name": _text(record["name"], "metric name"),
        "value": _text(record["value"], "metric value"),
        "period": _text(record["period"], "metric period", allow_empty=True),
        "caveat": _text(record["caveat"], "metric caveat", allow_empty=True),
    }


def _validate_implementation(record: object) -> dict[str, object]:
    if not _exact_keys(record, ("availability", "uri")):
        raise ResearchIntakeError("implementation schema is invalid")
    if record["availability"] not in IMPLEMENTATION_AVAILABILITY:
        raise ResearchIntakeError("implementation availability is invalid")
    uri = _https_uri(record["uri"], "implementation uri", nullable=True)
    if record["availability"] == "NONE" and uri is not None:
        raise ResearchIntakeError("NONE implementation cannot have a URI")
    if record["availability"] != "NONE" and uri is None:
        raise ResearchIntakeError("available implementation requires a URI")
    return dict(record)


def _validate_candidate(candidate: object) -> dict[str, object]:
    keys = (
        "candidate_id",
        "source",
        "technique_family",
        "market_universe",
        "timeframes",
        "hypothesis",
        "entry_rules",
        "exit_rules",
        "stop_rules",
        "sizing_rules",
        "lookbacks",
        "cost_assumptions",
        "reported_metrics",
        "implementation",
        "known_limitations",
        "leakage_risks",
        "status",
        "duplicate_of",
        "strategy_evidence_effect",
        "p10_evidence_effect",
    )
    if not _exact_keys(candidate, keys):
        raise ResearchIntakeError("candidate schema is invalid")
    candidate_id = candidate["candidate_id"]
    if (
        not isinstance(candidate_id, str)
        or CANDIDATE_ID_RE.fullmatch(candidate_id) is None
    ):
        raise ResearchIntakeError("candidate identity is invalid")

    _validate_source(candidate["source"])
    if candidate["technique_family"] not in TECHNIQUE_FAMILIES:
        raise ResearchIntakeError("technique family is invalid")
    market_universe = _text_list(
        candidate["market_universe"], "market universe", required=True
    )
    timeframes = _text_list(
        candidate["timeframes"], "timeframes", required=True
    )
    _text(candidate["hypothesis"], "hypothesis")
    entry_rules = _text_list(candidate["entry_rules"], "entry rules")
    exit_rules = _text_list(candidate["exit_rules"], "exit rules")
    _text_list(candidate["stop_rules"], "stop rules")
    _text_list(candidate["sizing_rules"], "sizing rules")
    _text_list(candidate["lookbacks"], "lookbacks")
    cost_assumptions = _text_list(
        candidate["cost_assumptions"], "cost assumptions"
    )

    metrics = candidate["reported_metrics"]
    if not isinstance(metrics, list) or len(metrics) > MAX_LIST_ITEMS:
        raise ResearchIntakeError("reported metrics list is invalid")
    [_validate_reported_metric(item) for item in metrics]
    _validate_implementation(candidate["implementation"])
    _text_list(candidate["known_limitations"], "known limitations")
    _text_list(candidate["leakage_risks"], "leakage risks")

    status = candidate["status"]
    if status not in STATUSES:
        raise ResearchIntakeError("candidate status is invalid")
    duplicate_of = candidate["duplicate_of"]
    if duplicate_of is not None and (
        not isinstance(duplicate_of, str)
        or CANDIDATE_ID_RE.fullmatch(duplicate_of) is None
    ):
        raise ResearchIntakeError("duplicate_of identity is invalid")
    if (
        candidate["strategy_evidence_effect"] != "NONE"
        or candidate["p10_evidence_effect"] != "NONE"
    ):
        raise ResearchIntakeError(
            "external research cannot create strategy or P10 evidence"
        )

    if status in {"REPRODUCIBLE", "READY_FOR_TRAIN_SEARCH"} and (
        not entry_rules or not exit_rules
    ):
        raise ResearchIntakeError(
            "reproducible/search-ready candidate needs entry and exit rules"
        )
    if status == "READY_FOR_TRAIN_SEARCH" and not cost_assumptions:
        raise ResearchIntakeError(
            "search-ready candidate needs explicit cost assumptions"
        )
    if status == "DUPLICATE" and duplicate_of is None:
        raise ResearchIntakeError("duplicate candidate must reference its original")
    if status != "DUPLICATE" and duplicate_of is not None:
        raise ResearchIntakeError(
            "non-duplicate candidate cannot reference duplicate_of"
        )
    if not market_universe or not timeframes:
        raise ResearchIntakeError("candidate market scope is missing")
    return dict(candidate)


def validate_registry(path: Path) -> dict[str, object]:
    if not isinstance(path, Path):
        raise ResearchIntakeError("registry path must be a Path")
    target = path.expanduser()
    if target.exists() and target.is_symlink():
        raise ResearchIntakeError("symlink registry is forbidden")
    try:
        payload = target.read_bytes()
    except OSError:
        raise ResearchIntakeError("cannot read candidate registry") from None
    if not payload or len(payload) > MAX_REGISTRY_BYTES:
        raise ResearchIntakeError("candidate registry size is invalid")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ResearchIntakeError(
            "candidate registry is not canonical UTF-8 JSON"
        ) from None

    top_keys = (
        "schema",
        "schema_version",
        "registry_id",
        "candidates",
        "research_only",
        "p10_read",
        "p10_write_allowed",
        "p10_evidence_effect",
        "trade_permission",
        "order_endpoint",
        "quantity_authority",
        "risk_authorization_mutation",
        "ai_direct_execution",
        "p11_locked",
    )
    if not _exact_keys(record, top_keys):
        raise ResearchIntakeError("candidate registry top-level schema is invalid")
    if (
        record["schema"] != SCHEMA
        or record["schema_version"] != SCHEMA_VERSION
        or record["registry_id"] != REGISTRY_ID
        or record["research_only"] is not True
        or record["p10_read"] is not False
        or record["p10_write_allowed"] is not False
        or record["p10_evidence_effect"] != "NONE"
        or record["trade_permission"] is not False
        or record["order_endpoint"] is not False
        or record["quantity_authority"] is not False
        or record["risk_authorization_mutation"] is not False
        or record["ai_direct_execution"] is not False
        or record["p11_locked"] is not True
    ):
        raise ResearchIntakeError("candidate registry safety invariants are invalid")

    candidates = record["candidates"]
    if (
        not isinstance(candidates, list)
        or len(candidates) > MAX_CANDIDATES
    ):
        raise ResearchIntakeError("candidate count is invalid")

    validated = [_validate_candidate(item) for item in candidates]
    ids = [item["candidate_id"] for item in validated]
    if len(set(ids)) != len(ids) or ids != sorted(ids):
        raise ResearchIntakeError(
            "candidate ids must be unique and sorted"
        )
    source_ids = [item["source"]["source_id"] for item in validated]
    if len(set(source_ids)) != len(source_ids):
        raise ResearchIntakeError("source ids must be unique")

    first_by_fingerprint: dict[str, str] = {}
    fingerprints: dict[str, str] = {}
    duplicate_count = 0
    for item in validated:
        candidate_id = str(item["candidate_id"])
        fingerprint = candidate_fingerprint(item)
        fingerprints[candidate_id] = fingerprint
        original = first_by_fingerprint.get(fingerprint)
        if original is None:
            if item["status"] == "DUPLICATE":
                raise ResearchIntakeError(
                    "duplicate candidate has no earlier matching hypothesis"
                )
            first_by_fingerprint[fingerprint] = candidate_id
            continue
        duplicate_count += 1
        if (
            item["status"] != "DUPLICATE"
            or item["duplicate_of"] != original
        ):
            raise ResearchIntakeError(
                "duplicate hypothesis must be explicitly linked"
            )

    status_counts = {
        status: sum(item["status"] == status for item in validated)
        for status in sorted(STATUSES)
    }
    tier_counts = {
        tier: sum(item["source"]["tier"] == tier for item in validated)
        for tier in sorted(SOURCE_TIERS)
    }
    return {
        "schema": "YATL_RESEARCH_CANDIDATE_REGISTRY_VALIDATION",
        "schema_version": SCHEMA_VERSION,
        "registry_id": REGISTRY_ID,
        "registry_file_sha256": _sha256(payload),
        "candidate_count": len(validated),
        "unique_hypothesis_count": len(first_by_fingerprint),
        "duplicate_count": duplicate_count,
        "status_counts": status_counts,
        "source_tier_counts": tier_counts,
        "candidate_fingerprints": fingerprints,
        "network_used": False,
        "external_performance_trusted": False,
        "strategy_evidence_effect": "NONE",
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "trade_permission": False,
        "order_endpoint": False,
        "quantity_authority": False,
        "risk_authorization_mutation": False,
        "ai_direct_execution": False,
        "p11_locked": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research.research_intake.registry",
        description="Validate the YATL research candidate registry",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--registry", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "validate":
        raise ResearchIntakeError("unsupported RIE command")
    print(_json(validate_registry(args.registry)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ResearchIntakeError as exc:
        print(
            _json(
                {
                    "code": "RIE001_CANDIDATE_REGISTRY_ERROR",
                    "reason": str(exc),
                    "research_only": True,
                    "p10_write_allowed": False,
                    "p11_locked": True,
                }
            )
        )
        raise SystemExit(2)
