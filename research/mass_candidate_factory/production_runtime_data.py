"""AF-01C selected-union runtime bars, before any candidate performance.

Only monthly ledger metadata is scanned outside the frozen union. Market CSVs
are read only for its members. No network acquisition or gap repair exists here.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from decimal import Context, localcontext
from pathlib import Path

from research.crisis_lab.acquisition import _canonical_csv
from research.opportunity_data.archive_adapter import STATES
from research.opportunity_data.canonical import validate_rows
from research.opportunity_data.models import sha256
from research.opportunity_data.pc_population import (
    SUCCESS_STATES, _load_bound_plan, _validate_ledger,
)
from research.opportunity_data.quality import gap_map
from research.opportunity_data.storage import read_canonical
from research.opportunity_data.views import derive

from .models import MCFError, canonical, digest, guard_root, safe_path, write_once
from .production import CADENCE_MS, DEVELOPMENT_END_MS, DEVELOPMENT_START_MS
from .production_features import POPULATION_START_MS
from .production_membership_freeze import (
    EXPECTED_PLAN_SHA256, EXPECTED_POPULATION_RECONCILIATION_SHA256,
    EXPECTED_SAFETY, _read_preflight, build_freeze,
)

VERSION = "MCF_PRODUCTION_RUNTIME_DATA/1.0.0"
MEMBERSHIP_SHA = "c75aa5c4347dff5daeed1ca2625fb86e2df3f4e105fde55aed0248df4ce868b7"
PREFLIGHT_SHA = "f0a177cc98d3946ead55dc69016d65178539ecd0c778c9c4ae0a193e3ba61cfc"
CLASSIFICATION_SHA = "e19cb8539c29e6a95c453b6a680b56b5b88bddad65df8a67ca32a14ceab41012"
TIMEFRAMES = ("15m", "1h", "4h")
SAFETY = {**EXPECTED_SAFETY, "paper_research_only": True,
          "live_master_lock": "OFF", "futures": False, "leverage": False,
          "short": False, "order_endpoint": False, "ai_direct_execution": False}
BOUNDS = {"population_start_ms": POPULATION_START_MS,
          "warmup_end_exclusive_ms": DEVELOPMENT_START_MS,
          "scoring_start_ms": DEVELOPMENT_START_MS,
          "development_end_exclusive_ms": DEVELOPMENT_END_MS}


def read_json(root: Path, relative: str) -> tuple[dict, bytes]:
    raw = safe_path(root, relative).read_bytes()
    doc = json.loads(raw)
    if not isinstance(doc, dict) or canonical(doc) != raw:
        raise MCFError("noncanonical runtime input JSON")
    return doc, raw


def read_hashed(root: Path, relative: str, expected: str, field: str) -> dict:
    doc, _ = read_json(root, relative)
    base = {k: v for k, v in doc.items() if k != field}
    if doc.get(field) != expected or digest(base) != expected:
        raise MCFError(f"runtime input identity mismatch: {field}")
    return doc


def read_membership(root: Path, relative: str, expected: str,
                    preflight_relative: str, preflight_sha: str) -> dict:
    doc = read_hashed(root, relative, expected, "freeze_sha256")
    preflight = _read_preflight(root, preflight_relative, preflight_sha)
    if canonical(build_freeze(preflight)) != canonical(doc):
        raise MCFError("membership differs from bound preflight")
    return doc


def accepted_membership(root: Path) -> dict:
    doc = read_membership(
        root, f"monthly-membership/membership-freeze-{MEMBERSHIP_SHA}.json",
        MEMBERSHIP_SHA, f"binding-preflight/preflight-{PREFLIGHT_SHA}.json",
        PREFLIGHT_SHA,
    )
    counts = Counter(x["selected_count"] for x in doc["monthly_memberships"])
    if (doc["selected_union_count"] != 175 or counts != {50: 22, 0: 11, 15: 1}
            or doc["classification_map_sha256"] != CLASSIFICATION_SHA):
        raise MCFError("accepted membership shape/classification mismatch")
    return doc


def verify_population_metadata(root: Path, plan: dict, reconciliation: dict) -> dict:
    """Reproduce the accepted aggregate ledger identity without other market reads."""
    records = {}
    ordered_hashes = []
    gaps = 0
    for entry in plan["periods"]:
        identity = f"{entry['symbol']}-{entry['month']}"
        doc, _ = read_json(root, f"ledger/{identity}.json")
        base = {k: v for k, v in doc.items() if k != "record_sha256"}
        if (digest(base) != doc.get("record_sha256") or identity in records
                or doc.get("identity") != identity or doc.get("symbol") != entry["symbol"]
                or doc.get("period") != entry["month"] or doc.get("interval") != "15m"
                or doc.get("plan_sha256") != plan["plan_sha256"]
                or doc.get("state") not in STATES):
            raise MCFError("AF-01C immutable population ledger mismatch")
        records[identity] = doc
        ordered_hashes.append(doc["record_sha256"])
        gaps += doc["state"] not in SUCCESS_STATES
    payload = {"state": "AF01C_ENGINEERING_PILOT_NO_SELECTION",
               "plan_sha256": plan["plan_sha256"], "records": tuple(ordered_hashes),
               "final_count": len(records), "source_gap_count": gaps}
    if (digest(payload) != reconciliation.get("adapter_reconciliation_sha256")
            or len(records) != 9306 or gaps != 2863
            or reconciliation.get("final_count") != 9306
            or reconciliation.get("source_gap_count") != 2863):
        raise MCFError("AF-01C accepted reconciliation no longer matches ledgers")
    return records


def symbol_source(root: Path, plan: dict, inventory: dict, entries: list,
                  records: dict) -> tuple[tuple, list[dict]]:
    rows, sources = [], []
    for entry in entries:
        identity = f"{entry['symbol']}-{entry['month']}"
        record = _validate_ledger(root, plan, inventory, entry)
        if record != records[identity]:
            raise MCFError("AF-01C ledger changed during materialization")
        source = {"identity": identity, "state": record["state"],
                  "record_sha256": record["record_sha256"],
                  "canonical_ref": record.get("canonical_ref"),
                  "canonical_sha256": record.get("canonical_sha256")}
        sources.append(source)
        if record["state"] not in SUCCESS_STATES:
            continue  # failure stays in provenance; never substitute partial bars
        part = read_canonical(root, record["canonical_ref"], record["canonical_sha256"])
        validate_development(part, "15m")
        if (len(part) != record["row_count"]
                or part[0].open_time_ms < record["requested_start_ms"]
                or part[-1].close_time_ms >= record["requested_end_ms"]
                or gap_map(part, entry["symbol"], "15m", "AF-01C/object").gap_count
                != record["gap_count"]):
            raise MCFError("monthly source boundary/count/gap mismatch")
        rows.extend(part)
    rows.sort(key=lambda row: row.open_time_ms)
    validate_development(rows, "15m")  # also rejects duplicates across months
    return tuple(rows), sources


def validate_development(rows, timeframe: str) -> None:
    if timeframe not in TIMEFRAMES:
        raise MCFError("unregistered runtime timeframe")
    validate_rows(rows, timeframe, as_of_ms=DEVELOPMENT_END_MS)
    if rows[0].open_time_ms < POPULATION_START_MS:
        raise MCFError("runtime data precedes registered population")


def full_gap_map(rows, symbol: str, timeframe: str, dataset_id: str) -> dict:
    """Every absent bucket over the FULL evidence interval, including its edges."""
    cadence = CADENCE_MS[timeframe]
    ranges, cursor = [], POPULATION_START_MS
    for row in rows:
        if row.open_time_ms > cursor:
            ranges.append((cursor, row.open_time_ms - cadence))
        cursor = row.open_time_ms + cadence
    if cursor < DEVELOPMENT_END_MS:
        ranges.append((cursor, DEVELOPMENT_END_MS - cadence))
    return {"schema": VERSION, "symbol": symbol, "timeframe": timeframe,
            "dataset_id": dataset_id, "evidence_bounds": BOUNDS,
            "cadence_ms": cadence, "missing_ranges": tuple(ranges),
            "gap_count": sum((b - a) // cadence + 1 for a, b in ranges),
            "repair": "NONE"}


def derive_complete(rows, symbol: str, timeframe: str, dataset_id: str):
    if timeframe == "15m":
        return tuple(rows), 0
    # Isolate the accepted algorithm from ambient Decimal context changes.
    with localcontext(Context(prec=28)):
        result, _ = derive(rows, symbol, dataset_id, "15m", timeframe,
                           as_of_ms=DEVELOPMENT_END_MS)
    bucket_count = len({r.open_time_ms // CADENCE_MS[timeframe] for r in rows})
    return result, bucket_count - len(result)


def materialize_symbol(output_root: Path, symbol: str, rows, sources: list[dict]) -> list[dict]:
    validate_development(rows, "15m")
    source_sha = sha256(_canonical_csv(rows))
    result = []
    for timeframe in TIMEFRAMES:
        dataset_id = f"MCF-PROD-001/{symbol}-{timeframe}/{source_sha}"
        derived, dropped = derive_complete(rows, symbol, timeframe, dataset_id)
        validate_development(derived, timeframe)
        if len(derived) < 2:
            raise MCFError("insufficient complete runtime buckets")
        raw = _canonical_csv(derived)
        data_sha = sha256(raw)
        gap = full_gap_map(derived, symbol, timeframe, dataset_id)
        gap_sha = digest(gap)
        prefix = f"runtime-data/{symbol}/{timeframe}"
        data_ref = f"{prefix}/canonical-{data_sha}.csv"
        gap_ref = f"{prefix}/gaps-{gap_sha}.json"
        write_once(safe_path(output_root, data_ref), raw)
        write_once(safe_path(output_root, gap_ref), canonical(gap))
        result.append({"symbol": symbol, "timeframe": timeframe,
                       "dataset_id": dataset_id, "row_count": len(derived),
                       "first_time_ms": derived[0].open_time_ms,
                       "last_time_ms": derived[-1].open_time_ms,
                       "content_sha256": data_sha, "data_ref": data_ref,
                       "gap_sha256": gap_sha, "gap_ref": gap_ref,
                       "gap_count": gap["gap_count"], "source_15m_sha256": source_sha,
                       "source_15m_records": sources,
                       "source_records_sha256": digest(sources),
                       "evidence_bounds": BOUNDS, "evidence_partition": "DEVELOPMENT",
                       "validity": "PASS_WITH_GAPS" if gap["gap_count"] else "PASS_CONTIGUOUS",
                       "incomplete_bucket_dropped_count": dropped})
    return result


def materialize(*, pc_root: Path, evidence_root: Path, output_root: Path,
                plan_relative: str, inventory_relative: str) -> dict:
    pc_root, evidence_root, output_root = map(guard_root, (pc_root, evidence_root, output_root))
    if any(not p.is_dir() for p in (pc_root, evidence_root, output_root)):
        raise MCFError("runtime roots must already exist")
    if output_root == pc_root or output_root.is_relative_to(pc_root) or pc_root.is_relative_to(output_root):
        raise MCFError("runtime output must be isolated from accepted AF-01C")
    membership = accepted_membership(evidence_root)
    plan, inventory = _load_bound_plan(pc_root, plan_relative, inventory_relative)
    if plan["plan_sha256"] != EXPECTED_PLAN_SHA256:
        raise MCFError("unaccepted AF-01C plan")
    relative = f"population/reconciliation-{EXPECTED_POPULATION_RECONCILIATION_SHA256}.json"
    reconciliation, raw = read_json(pc_root, relative)
    if sha256(raw) != EXPECTED_POPULATION_RECONCILIATION_SHA256:
        raise MCFError("unaccepted AF-01C population reconciliation")
    records = verify_population_metadata(pc_root, plan, reconciliation)
    grouped = defaultdict(list)
    for entry in plan["periods"]:
        grouped[entry["symbol"]].append(entry)
    datasets = []
    for symbol in membership["selected_union_symbols"]:
        if not grouped[symbol]:
            raise MCFError("selected symbol missing from population")
        rows, sources = symbol_source(pc_root, plan, inventory, grouped[symbol], records)
        datasets.extend(materialize_symbol(output_root, symbol, rows, sources))
        del rows
    base = {"schema": VERSION, "generation_id": "MCF-PROD-001",
            "state": "RUNTIME_DATA_MATERIALIZED_BEFORE_PERFORMANCE",
            "membership_freeze_sha256": MEMBERSHIP_SHA,
            "source_preflight_sha256": PREFLIGHT_SHA,
            "classification_map_sha256": CLASSIFICATION_SHA,
            "plan_sha256": EXPECTED_PLAN_SHA256,
            "population_reconciliation_sha256": EXPECTED_POPULATION_RECONCILIATION_SHA256,
            "universe_policy_sha256": membership["universe_policy_sha256"],
            "selected_union_symbols": membership["selected_union_symbols"],
            "dataset_count": len(datasets), "timeframes": TIMEFRAMES,
            "evidence_bounds": BOUNDS, "datasets": datasets, "safety": SAFETY}
    index = {**base, "index_sha256": digest(base)}
    relative = f"runtime-data/index-{index['index_sha256']}.json"
    write_once(safe_path(output_root, relative), canonical(index))
    return {"status": base["state"], "artifact": relative,
            "index_sha256": index["index_sha256"], "dataset_count": len(datasets),
            "safety": SAFETY}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pc-root", "evidence-root", "output-root"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--plan-relative", required=True)
    parser.add_argument("--inventory-relative", required=True)
    args = parser.parse_args(argv)
    try:
        result = materialize(**vars(args))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "RUNTIME_DATA_BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
