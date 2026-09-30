"""Freeze exact MCF-PROD-001 point-in-time monthly memberships.

Pre-performance governance only. This consumes one accepted
READY_FOR_PRODUCTION_BINDING preflight artifact, validates its exact identity and
safety boundary, then writes a content-addressed membership freeze. It does not
read candidate performance, Fresh OOS, recent reserve, P10, or Live state.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import MCFError, canonical, digest, guard_root, safe_path, write_once
from .production_binding_preflight import (
    EXPECTED_POPULATION_RECONCILIATION_SHA256,
    VERSION as PREFLIGHT_SCHEMA,
    _month_starts,
)
from .production_generator import UNIVERSE_POLICY_SHA256

VERSION = "MCF_PRODUCTION_MONTHLY_MEMBERSHIP_FREEZE/1.0.0"
GENERATION_ID = "MCF-PROD-001"
EXPECTED_PLAN_SHA256 = (
    "5bc6fc2baa8e32d096c88e755763a79e222f1c7a43d0649e5074fd969b4d296a"
)
EXPECTED_SAFETY = {
    "performance_read": False,
    "fresh_oos_read": False,
    "recent_reserve_read": False,
    "p10_read": False,
    "p10_write": False,
    "live": False,
    "p11_locked": True,
}


def _sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _read_preflight(
    root: Path,
    relative: str,
    expected_preflight_sha256: str,
) -> dict:
    root = guard_root(root)
    path = safe_path(root, relative)
    if not path.is_file() or path.is_symlink():
        raise MCFError("missing production-binding preflight artifact")
    raw = path.read_bytes()
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise MCFError("invalid production-binding preflight JSON") from exc
    if not isinstance(doc, dict) or canonical(doc) != raw:
        raise MCFError("noncanonical production-binding preflight artifact")
    if not _sha(expected_preflight_sha256):
        raise MCFError("invalid expected preflight identity")
    claimed = doc.get("preflight_sha256")
    if claimed != expected_preflight_sha256:
        raise MCFError("production-binding preflight identity mismatch")
    base = dict(doc)
    base.pop("preflight_sha256", None)
    if digest(base) != claimed:
        raise MCFError("production-binding preflight digest mismatch")
    return doc


def _validate_ready_preflight(doc: dict) -> tuple[tuple[dict, ...], tuple[str, ...]]:
    if (
        doc.get("schema") != PREFLIGHT_SCHEMA
        or doc.get("generation_id") != GENERATION_ID
        or doc.get("state") != "READY_FOR_PRODUCTION_BINDING"
        or doc.get("plan_sha256") != EXPECTED_PLAN_SHA256
        or doc.get("population_reconciliation_sha256")
        != EXPECTED_POPULATION_RECONCILIATION_SHA256
        or doc.get("universe_policy_sha256") != UNIVERSE_POLICY_SHA256
        or not _sha(doc.get("classification_map_sha256"))
        or doc.get("membership_resolved") is not True
        or doc.get("next_classification_frontier_symbol_count") != 0
        or tuple(doc.get("next_classification_frontier_symbols", ())) != ()
        or doc.get("safety") != EXPECTED_SAFETY
    ):
        raise MCFError("preflight is not ready for monthly membership freeze")

    monthly = doc.get("monthly_rankings")
    if not isinstance(monthly, list):
        raise MCFError("preflight monthly rankings are missing")
    expected_months = _month_starts()
    if doc.get("month_count") != len(expected_months) or len(monthly) != len(expected_months):
        raise MCFError("preflight month count mismatch")

    frozen = []
    union: set[str] = set()
    for expected_ms, row in zip(expected_months, monthly):
        if not isinstance(row, dict) or row.get("effective_ms") != expected_ms:
            raise MCFError("monthly membership effective time mismatch")
        symbols = row.get("selected_symbols")
        if not isinstance(symbols, list):
            raise MCFError("monthly membership symbols are invalid")
        symbols_tuple = tuple(symbols)
        if (
            tuple(sorted(set(symbols_tuple))) != symbols_tuple
            or any(not isinstance(symbol, str) or not symbol.endswith("USDT") for symbol in symbols_tuple)
            or row.get("selected_count") != len(symbols_tuple)
            or len(symbols_tuple) > 50
            or not _sha(row.get("ranking_sha256"))
        ):
            raise MCFError("monthly membership row is invalid")
        dt = datetime.fromtimestamp(expected_ms / 1000, timezone.utc)
        if not (
            dt.day == 1
            and dt.hour == 0
            and dt.minute == 0
            and dt.second == 0
            and dt.microsecond == 0
        ):
            raise MCFError("monthly membership boundary is not UTC month start")

        membership_payload = {
            "effective_ms": expected_ms,
            "ranking_sha256": row["ranking_sha256"],
            "selected_symbols": symbols_tuple,
            "source_preflight_sha256": doc["preflight_sha256"],
            "universe_policy_sha256": doc["universe_policy_sha256"],
        }
        frozen.append({
            "effective_ms": expected_ms,
            "selected_count": len(symbols_tuple),
            "selected_symbols": symbols_tuple,
            "ranking_sha256": row["ranking_sha256"],
            "membership_sha256": digest(membership_payload),
        })
        union.update(symbols_tuple)

    return tuple(frozen), tuple(sorted(union))


def build_freeze(doc: dict) -> dict:
    monthly, union = _validate_ready_preflight(doc)
    base = {
        "schema": VERSION,
        "generation_id": GENERATION_ID,
        "state": "MONTHLY_MEMBERSHIP_FROZEN_BEFORE_RUNTIME_MATERIALIZATION",
        "source_preflight_sha256": doc["preflight_sha256"],
        "classification_map_sha256": doc["classification_map_sha256"],
        "plan_sha256": doc["plan_sha256"],
        "population_reconciliation_sha256":
            doc["population_reconciliation_sha256"],
        "universe_policy_sha256": doc["universe_policy_sha256"],
        "month_count": len(monthly),
        "monthly_memberships": monthly,
        "selected_union_count": len(union),
        "selected_union_symbols": union,
        "classification_complete": doc["classification_complete"],
        "unresolved_data_eligible_symbol_count":
            doc["unresolved_data_eligible_symbol_count"],
        "safety": EXPECTED_SAFETY,
    }
    return {**base, "freeze_sha256": digest(base)}


def materialize(
    *,
    preflight_root: Path,
    preflight_artifact: str,
    expected_preflight_sha256: str,
    output_root: Path,
) -> dict:
    output_root = guard_root(output_root)
    if not output_root.is_dir():
        raise MCFError("membership output root must already exist")
    doc = _read_preflight(
        preflight_root,
        preflight_artifact,
        expected_preflight_sha256,
    )
    freeze = build_freeze(doc)
    relative = (
        "monthly-membership/"
        f"membership-freeze-{freeze['freeze_sha256']}.json"
    )
    write_once(safe_path(output_root, relative), canonical(freeze))
    return {
        "status": freeze["state"],
        "artifact": relative,
        "freeze_sha256": freeze["freeze_sha256"],
        "source_preflight_sha256": freeze["source_preflight_sha256"],
        "classification_map_sha256": freeze["classification_map_sha256"],
        "month_count": freeze["month_count"],
        "selected_union_count": freeze["selected_union_count"],
        "classification_complete": freeze["classification_complete"],
        "unresolved_data_eligible_symbol_count":
            freeze["unresolved_data_eligible_symbol_count"],
        "performance_read": False,
        "fresh_oos_read": False,
        "recent_reserve_read": False,
        "p10_read": False,
        "p10_write": False,
        "live": False,
        "p11_locked": True,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-root", required=True, type=Path)
    parser.add_argument("--preflight-artifact", required=True)
    parser.add_argument("--expected-preflight-sha256", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = materialize(
            preflight_root=args.preflight_root,
            preflight_artifact=args.preflight_artifact,
            expected_preflight_sha256=args.expected_preflight_sha256,
            output_root=args.output_root,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError) as exc:
        print(json.dumps({
            "status": "MONTHLY_MEMBERSHIP_FREEZE_BLOCKED",
            "reason": str(exc),
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
