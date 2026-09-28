"""AF-01C P-C isolated, restartable broad-population execution helpers."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from research.mass_candidate_factory.models import guard_root

from .archive_adapter import (
    STATES,
    _bound_entry,
    _verify_record_binding,
    acquire_period,
    plan,
    reconcile,
    verify_plan,
)
from .archive_inventory import verify
from .models import OpportunityError, canonical, development_path, digest, sha256
from .storage import save_artifact

FROZEN_SNAPSHOT_SHA256 = "3c27c203e188095cc6a0f1ab7bafbd9bd534ed786bccf8cfe3c240644ccedeb6"
FROZEN_NORMALIZED_INVENTORY_SHA256 = "83aba891ce5163d372ade6021950277ae335c0455e16eb9d5dd88fd050f671cf"
FROZEN_AUDIT_SHA256 = "cc5221fc79c0a35bace700603f7b8332eef842d5dd0e4b918017d7af9785cf5d"
FROZEN_SYMBOL_COUNT = 413
FROZEN_PERIOD_COUNT = 9306
MAX_CANARY_BATCH = 25
SUCCESS_STATES = frozenset({"MONTHLY_SUCCESS", "DAILY_FALLBACK_SUCCESS"})
MONTHS = tuple(
    f"{year}-{month:02d}"
    for year in (2020, 2021, 2022)
    for month in range(1, 13)
)


def _read_json(root: Path, relative: str) -> tuple[dict, bytes]:
    path = development_path(root, relative)
    try:
        raw = path.read_bytes()
        document = json.loads(raw)
    except (OSError, ValueError, UnicodeError) as exc:
        raise OpportunityError("missing/invalid P-C artifact") from exc
    if not isinstance(document, dict) or canonical(document) != raw:
        raise OpportunityError("noncanonical P-C artifact")
    return document, raw


def bootstrap_pc(
    source_root: Path,
    target_root: Path,
    inventory_relative: str,
    audit_relative: str,
    *,
    expected_snapshot_sha256: str = FROZEN_SNAPSHOT_SHA256,
    expected_normalized_sha256: str = FROZEN_NORMALIZED_INVENTORY_SHA256,
    expected_audit_sha256: str = FROZEN_AUDIT_SHA256,
) -> dict:
    """Copy only frozen P-A evidence into an isolated P-C root after verification."""
    guard_root(source_root)
    guard_root(target_root)
    source = source_root.resolve()
    target = target_root.resolve()
    if source == target or source.is_relative_to(target) or target.is_relative_to(source):
        raise OpportunityError("P-C runtime root is not isolated")
    if not source_root.is_dir():
        raise OpportunityError("P-B evidence root missing")
    target_root.mkdir(parents=True, exist_ok=True)

    inventory, inventory_raw = _read_json(source_root, inventory_relative)
    verify(inventory)
    if (
        sha256(inventory_raw) != expected_snapshot_sha256
        or inventory.get("normalized_inventory_sha256") != expected_normalized_sha256
    ):
        raise OpportunityError("frozen P-A inventory binding mismatch")

    audit, audit_raw = _read_json(source_root, audit_relative)
    if (
        sha256(audit_raw) != expected_audit_sha256
        or audit.get("schema") != "AF-01C-INDEPENDENT-RAW-REPLAY-AUDIT/1"
        or audit.get("state") != "PASS"
        or audit.get("snapshot_sha256") != expected_snapshot_sha256
        or audit.get("normalized_inventory_sha256") != expected_normalized_sha256
    ):
        raise OpportunityError("frozen P-A audit binding mismatch")

    save_artifact(target_root, inventory_relative, inventory_raw)
    save_artifact(target_root, audit_relative, audit_raw)

    base = dict(
        schema="AF-01C-PC-BOOTSTRAP/1",
        state="BOOTSTRAPPED",
        inventory_ref=inventory_relative,
        inventory_sha256=expected_snapshot_sha256,
        normalized_inventory_sha256=expected_normalized_sha256,
        audit_ref=audit_relative,
        audit_sha256=expected_audit_sha256,
        source_root=str(source),
        target_root=str(target),
    )
    manifest_sha = digest(base)
    save_artifact(
        target_root,
        f"bootstrap/bootstrap-{manifest_sha}.json",
        canonical(base),
    )
    return base | {"bootstrap_sha256": manifest_sha}


def create_pc_plan(
    root: Path,
    inventory_relative: str,
    *,
    expected_snapshot_sha256: str = FROZEN_SNAPSHOT_SHA256,
    expected_normalized_sha256: str = FROZEN_NORMALIZED_INVENTORY_SHA256,
    expected_symbol_count: int = FROZEN_SYMBOL_COUNT,
    expected_period_count: int = FROZEN_PERIOD_COUNT,
) -> dict:
    inventory, raw = _read_json(root, inventory_relative)
    verify(inventory)
    if (
        sha256(raw) != expected_snapshot_sha256
        or inventory.get("normalized_inventory_sha256") != expected_normalized_sha256
    ):
        raise OpportunityError("P-C inventory is not the frozen P-A snapshot")

    symbols = tuple(sorted({item["symbol"] for item in inventory["objects"]}))
    if len(symbols) != expected_symbol_count:
        raise OpportunityError("P-C symbol cardinality mismatch")

    population_plan = plan(inventory, symbols, MONTHS, pilot=False)
    verify_plan(population_plan, inventory)
    monthly_count = sum(1 for entry in population_plan["periods"] if entry["monthly"])
    daily_only_count = sum(
        1 for entry in population_plan["periods"]
        if not entry["monthly"] and entry["daily"]
    )
    if (
        population_plan.get("state") != "REGISTERED_DEVELOPMENT"
        or len(population_plan["periods"]) != expected_period_count
        or monthly_count != expected_period_count
        or daily_only_count != 0
    ):
        raise OpportunityError("P-C frozen plan cardinality mismatch")

    relative = f"plans/plan-{population_plan['plan_sha256']}.json"
    save_artifact(root, relative, canonical(population_plan))
    return dict(
        state="P_C_PLAN_FROZEN",
        plan_ref=relative,
        plan_sha256=population_plan["plan_sha256"],
        symbol_count=len(symbols),
        period_count=len(population_plan["periods"]),
        monthly_period_count=monthly_count,
        daily_only_period_count=daily_only_count,
    )


def _load_bound_plan(root: Path, plan_relative: str, inventory_relative: str) -> tuple[dict, dict]:
    inventory, _ = _read_json(root, inventory_relative)
    verify(inventory)
    population_plan, _ = _read_json(root, plan_relative)
    verify_plan(population_plan, inventory)
    if population_plan.get("state") != "REGISTERED_DEVELOPMENT":
        raise OpportunityError("P-C requires registered Development plan")
    return population_plan, inventory


def _validate_ledger(root: Path, population_plan: dict, inventory: dict, entry: dict) -> dict:
    path = root / "ledger" / f"{entry['symbol']}-{entry['month']}.json"
    try:
        raw = path.read_bytes()
        record = json.loads(raw)
    except (OSError, ValueError, UnicodeError) as exc:
        raise OpportunityError("invalid P-C ledger") from exc
    if canonical(record) != raw:
        raise OpportunityError("noncanonical P-C ledger")
    base = {key: value for key, value in record.items() if key != "record_sha256"}
    if digest(base) != record.get("record_sha256"):
        raise OpportunityError("P-C ledger digest mismatch")
    _verify_record_binding(
        root,
        record,
        entry,
        _bound_entry(population_plan, inventory, entry),
    )
    if (
        record.get("identity") != f"{entry['symbol']}-{entry['month']}"
        or record.get("state") not in STATES
    ):
        raise OpportunityError("invalid P-C ledger final state")
    return record


def population_status(root: Path, plan_relative: str, inventory_relative: str) -> dict:
    population_plan, inventory = _load_bound_plan(root, plan_relative, inventory_relative)
    counts: Counter[str] = Counter()
    completed = 0
    artifact_refs: set[str] = set()

    for entry in population_plan["periods"]:
        path = root / "ledger" / f"{entry['symbol']}-{entry['month']}.json"
        if not path.is_file():
            continue
        record = _validate_ledger(root, population_plan, inventory, entry)
        completed += 1
        counts[record["state"]] += 1
        artifact_refs.update(record.get("artifact_hashes", {}))

    artifact_bytes = 0
    for relative in artifact_refs:
        path = development_path(root, relative)
        if not path.is_file():
            raise OpportunityError("P-C ledger references missing artifact")
        artifact_bytes += path.stat().st_size

    total = len(population_plan["periods"])
    remaining = total - completed
    success_count = sum(counts[state] for state in SUCCESS_STATES)
    source_gap_count = completed - success_count
    base = dict(
        schema="AF-01C-PC-STATUS/1",
        state="P_C_READY_TO_RECONCILE" if remaining == 0 else "P_C_IN_PROGRESS",
        plan_sha256=population_plan["plan_sha256"],
        total_identities=total,
        completed_identities=completed,
        remaining_identities=remaining,
        success_count=success_count,
        source_gap_or_failure_count=source_gap_count,
        state_counts=dict(sorted(counts.items())),
        artifact_bytes=artifact_bytes,
    )
    return base | {"status_sha256": digest(base)}


def acquire_batch(
    root: Path,
    plan_relative: str,
    inventory_relative: str,
    *,
    limit: int,
    allow_daily_fallback: bool = True,
    fetcher=None,
    retrieved_ms: int | None = None,
) -> dict:
    if not isinstance(limit, int) or not 1 <= limit <= MAX_CANARY_BATCH:
        raise OpportunityError("P-C canary batch limit exceeded")
    population_plan, inventory = _load_bound_plan(root, plan_relative, inventory_relative)

    missing = []
    for entry in population_plan["periods"]:
        path = root / "ledger" / f"{entry['symbol']}-{entry['month']}.json"
        if path.is_file():
            _validate_ledger(root, population_plan, inventory, entry)
            continue
        missing.append(entry)
        if len(missing) == limit:
            break

    if retrieved_ms is None:
        retrieved_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    records = []
    for entry in missing:
        record = acquire_period(
            root,
            entry,
            fetcher=fetcher,
            plan_doc=population_plan,
            inventory=inventory,
            retrieved_ms=retrieved_ms,
            allow_daily_fallback=allow_daily_fallback,
        )
        records.append(record)

    batch_base = dict(
        schema="AF-01C-PC-BATCH/1",
        state="P_C_CANARY_BATCH_COMPLETE",
        plan_sha256=population_plan["plan_sha256"],
        requested_limit=limit,
        acquired_count=len(records),
        identities=tuple(record["identity"] for record in records),
        records=tuple(record["record_sha256"] for record in records),
        state_counts=dict(sorted(Counter(record["state"] for record in records).items())),
    )
    batch_sha = digest(batch_base)
    save_artifact(root, f"batches/batch-{batch_sha}.json", canonical(batch_base))
    status = population_status(root, plan_relative, inventory_relative)
    return batch_base | {
        "batch_sha256": batch_sha,
        "batch_ref": f"batches/batch-{batch_sha}.json",
        "population_status": status,
    }


def reconcile_population(root: Path, plan_relative: str, inventory_relative: str) -> dict:
    population_plan, inventory = _load_bound_plan(root, plan_relative, inventory_relative)
    status = population_status(root, plan_relative, inventory_relative)
    if status["remaining_identities"] != 0:
        raise OpportunityError("P-C population is incomplete")
    reconciled = reconcile(root, population_plan, inventory)
    state = (
        "POPULATION_COMPLETE"
        if reconciled["source_gap_count"] == 0
        else "POPULATION_COMPLETE_WITH_SOURCE_GAPS"
    )
    base = dict(
        schema="AF-01C-PC-RECONCILIATION/1",
        state=state,
        plan_sha256=population_plan["plan_sha256"],
        final_count=reconciled["final_count"],
        source_gap_count=reconciled["source_gap_count"],
        adapter_reconciliation_sha256=reconciled["reconciliation_sha256"],
        status_sha256=status["status_sha256"],
    )
    manifest_sha = digest(base)
    save_artifact(root, f"population/reconciliation-{manifest_sha}.json", canonical(base))
    return base | {"population_reconciliation_sha256": manifest_sha}
