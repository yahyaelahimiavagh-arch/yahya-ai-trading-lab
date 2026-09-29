"""AF-01C P-C isolated, restartable broad-population execution helpers."""
from __future__ import annotations

import json
import shutil
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from research.mass_candidate_factory.models import guard_root

from .archive_adapter import (
    STATES,
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
MAX_FAST_BATCHES = 40
MAX_FAST_WORKERS = 4
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


def _bound_entry_from_verified_plan(population_plan: dict, entry: dict) -> dict:
    """Build the immutable ledger binding after the caller has verified the full plan once."""
    selected = (
        ([entry["monthly"]["key"]] if entry["monthly"] else [])
        + [item["key"] for item in entry["daily"]]
    )
    return dict(
        inventory_sha256=population_plan["inventory_sha256"],
        plan_sha256=population_plan["plan_sha256"],
        entry_sha256=digest(entry),
        selected_object_keys=selected,
    )


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
        _bound_entry_from_verified_plan(population_plan, entry),
    )
    if (
        record.get("identity") != f"{entry['symbol']}-{entry['month']}"
        or record.get("state") not in STATES
    ):
        raise OpportunityError("invalid P-C ledger final state")
    return record


def _status_from_verified_scan(
    population_plan: dict,
    counts: Counter[str],
    completed: int,
    artifact_bytes: int,
) -> dict:
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


def _scan_population(
    root: Path,
    population_plan: dict,
    inventory: dict,
) -> tuple[Counter[str], int, set[str], int, list[dict]]:
    """Verify each existing immutable ledger once and derive restart state from it."""
    counts: Counter[str] = Counter()
    completed = 0
    artifact_refs: set[str] = set()
    missing: list[dict] = []

    for entry in population_plan["periods"]:
        path = root / "ledger" / f"{entry['symbol']}-{entry['month']}.json"
        if not path.is_file():
            missing.append(entry)
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

    return counts, completed, artifact_refs, artifact_bytes, missing


def _extend_artifact_accounting(
    root: Path,
    artifact_refs: set[str],
    artifact_bytes: int,
    records: list[dict],
) -> int:
    for record in records:
        for relative in record.get("artifact_hashes", {}):
            if relative in artifact_refs:
                continue
            path = development_path(root, relative)
            if not path.is_file():
                raise OpportunityError("P-C ledger references missing artifact")
            artifact_refs.add(relative)
            artifact_bytes += path.stat().st_size
    return artifact_bytes


def population_status(root: Path, plan_relative: str, inventory_relative: str) -> dict:
    population_plan, inventory = _load_bound_plan(root, plan_relative, inventory_relative)
    counts, completed, _, artifact_bytes, _ = _scan_population(
        root,
        population_plan,
        inventory,
    )
    return _status_from_verified_scan(
        population_plan,
        counts,
        completed,
        artifact_bytes,
    )


def _tree_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for candidate in path.rglob("*"):
        if candidate.is_file() and not candidate.is_symlink():
            total += candidate.stat().st_size
    return total


def storage_preflight(source_root: Path, target_root: Path, *, period_count: int = FROZEN_PERIOD_COUNT) -> dict:
    """Persist a conservative disk-capacity gate based on real P-B successful artifacts."""
    guard_root(source_root)
    guard_root(target_root)
    if not source_root.is_dir() or not target_root.is_dir():
        raise OpportunityError("storage preflight root missing")
    source = source_root.resolve()
    target = target_root.resolve()
    if source == target or source.is_relative_to(target) or target.is_relative_to(source):
        raise OpportunityError("storage preflight roots are not isolated")

    sizes = []
    ledger_root = source_root / "ledger"
    for ledger in sorted(ledger_root.glob("*.json")):
        try:
            record = json.loads(ledger.read_bytes())
        except (OSError, ValueError, UnicodeError) as exc:
            raise OpportunityError("invalid P-B ledger during storage preflight") from exc
        if record.get("state") not in SUCCESS_STATES:
            continue
        refs = set(record.get("artifact_hashes", {}))
        if record.get("canonical_ref"):
            refs.add(record["canonical_ref"])
        size = 0
        for relative in refs:
            path = development_path(source_root, relative)
            if not path.is_file():
                raise OpportunityError("P-B storage sample references missing artifact")
            size += path.stat().st_size
        sizes.append(size)

    if not sizes:
        raise OpportunityError("no successful P-B storage sample")
    usage = shutil.disk_usage(target_root)
    average = int(sum(sizes) / len(sizes))
    maximum = max(sizes)
    estimate_average_x2 = average * period_count * 2
    estimate_max_x1_25 = maximum * period_count * 5 // 4
    required = max(estimate_average_x2, estimate_max_x1_25)
    state = "PASS" if usage.free > required else "BLOCKED"

    base = dict(
        schema="AF-01C-PC-STORAGE-PREFLIGHT/1",
        state=state,
        filesystem_total_bytes=usage.total,
        filesystem_used_bytes=usage.used,
        filesystem_free_bytes=usage.free,
        source_root_bytes=_tree_size(source_root),
        target_root_bytes=_tree_size(target_root),
        pilot_success_sample_count=len(sizes),
        pilot_average_artifact_bytes_per_period=average,
        pilot_max_artifact_bytes_per_period=maximum,
        period_count=period_count,
        estimate_average_x2_bytes=estimate_average_x2,
        estimate_max_x1_25_bytes=estimate_max_x1_25,
        conservative_required_bytes=required,
    )
    preflight_sha = digest(base)
    relative = f"preflight/storage-{preflight_sha}.json"
    save_artifact(target_root, relative, canonical(base))
    return base | {"preflight_sha256": preflight_sha, "preflight_ref": relative}


def _verify_storage_preflight(root: Path, relative: str) -> dict:
    try:
        document, _ = _read_json(root, relative)
    except OpportunityError as exc:
        raise OpportunityError("P-C storage preflight missing/invalid") from exc
    if (
        document.get("schema") != "AF-01C-PC-STORAGE-PREFLIGHT/1"
        or document.get("state") != "PASS"
        or not isinstance(document.get("conservative_required_bytes"), int)
        or document["conservative_required_bytes"] <= 0
    ):
        raise OpportunityError("P-C storage preflight not accepted")
    current = shutil.disk_usage(root)
    if current.free <= document["conservative_required_bytes"]:
        raise OpportunityError("P-C storage capacity no longer satisfies frozen preflight")
    return document


def accept_canary_continuation(
    root: Path,
    plan_relative: str,
    inventory_relative: str,
    canary_batch_relative: str,
    *,
    ci_head_sha: str,
    ci_run_id: int,
    ci_workflow: str,
) -> dict:
    """Freeze the completed <=25 canary and explicit external CI evidence before broad continuation."""
    population_plan, _ = _load_bound_plan(root, plan_relative, inventory_relative)
    status = population_status(root, plan_relative, inventory_relative)
    if (
        status["completed_identities"] != MAX_CANARY_BATCH
        or status["total_identities"] <= MAX_CANARY_BATCH
    ):
        raise OpportunityError("P-C canary is not exactly complete at continuation boundary")

    batch, batch_raw = _read_json(root, canary_batch_relative)
    batch_sha = sha256(batch_raw)
    expected_ref = f"batches/batch-{batch_sha}.json"
    if (
        canary_batch_relative != expected_ref
        or batch.get("schema") != "AF-01C-PC-BATCH/1"
        or batch.get("state") != "P_C_CANARY_BATCH_COMPLETE"
        or batch.get("plan_sha256") != population_plan["plan_sha256"]
        or batch.get("acquired_count") != MAX_CANARY_BATCH
        or len(batch.get("identities", ())) != MAX_CANARY_BATCH
        or len(batch.get("records", ())) != MAX_CANARY_BATCH
    ):
        raise OpportunityError("P-C canary batch evidence invalid")

    if (
        not isinstance(ci_head_sha, str)
        or len(ci_head_sha) != 40
        or any(ch not in "0123456789abcdef" for ch in ci_head_sha.lower())
        or not isinstance(ci_run_id, int)
        or ci_run_id <= 0
        or not isinstance(ci_workflow, str)
        or not ci_workflow.strip()
    ):
        raise OpportunityError("P-C continuation CI evidence invalid")

    base = dict(
        schema="AF-01C-PC-CONTINUATION-ACCEPTANCE/1",
        state="P_C_BROAD_CONTINUATION_ACCEPTED",
        plan_sha256=population_plan["plan_sha256"],
        canary_batch_ref=canary_batch_relative,
        canary_batch_sha256=batch_sha,
        canary_status_sha256=status["status_sha256"],
        canary_completed_identities=MAX_CANARY_BATCH,
        ci_head_sha=ci_head_sha.lower(),
        ci_run_id=ci_run_id,
        ci_workflow=ci_workflow.strip(),
        ci_conclusion="success",
    )
    acceptance_sha = digest(base)
    relative = f"continuation/acceptance-{acceptance_sha}.json"
    save_artifact(root, relative, canonical(base))
    return base | {
        "continuation_acceptance_sha256": acceptance_sha,
        "continuation_acceptance_ref": relative,
    }


def _verify_continuation_acceptance(
    root: Path,
    relative: str,
    population_plan: dict,
    current_status: dict,
) -> dict:
    try:
        document, raw = _read_json(root, relative)
    except OpportunityError as exc:
        raise OpportunityError("P-C continuation acceptance missing/invalid") from exc
    if (
        document.get("schema") != "AF-01C-PC-CONTINUATION-ACCEPTANCE/1"
        or document.get("state") != "P_C_BROAD_CONTINUATION_ACCEPTED"
        or document.get("plan_sha256") != population_plan["plan_sha256"]
        or document.get("canary_completed_identities") != MAX_CANARY_BATCH
        or document.get("ci_conclusion") != "success"
        or not isinstance(document.get("ci_run_id"), int)
        or document["ci_run_id"] <= 0
        or not isinstance(document.get("ci_head_sha"), str)
        or len(document["ci_head_sha"]) != 40
        or relative != f"continuation/acceptance-{sha256(raw)}.json"
        or current_status["completed_identities"] < MAX_CANARY_BATCH
    ):
        raise OpportunityError("P-C continuation acceptance not accepted")

    batch_ref = document.get("canary_batch_ref")
    if not isinstance(batch_ref, str):
        raise OpportunityError("P-C continuation canary reference invalid")
    batch, batch_raw = _read_json(root, batch_ref)
    if (
        sha256(batch_raw) != document.get("canary_batch_sha256")
        or batch.get("schema") != "AF-01C-PC-BATCH/1"
        or batch.get("state") != "P_C_CANARY_BATCH_COMPLETE"
        or batch.get("plan_sha256") != population_plan["plan_sha256"]
        or batch.get("acquired_count") != MAX_CANARY_BATCH
    ):
        raise OpportunityError("P-C continuation canary evidence collision")
    return document


def _acquire_verified_entries(
    root: Path,
    population_plan: dict,
    inventory: dict,
    entries: list[dict],
    *,
    allow_daily_fallback: bool,
    fetcher,
    retrieved_ms: int,
    workers: int = 1,
) -> list[dict]:
    if not isinstance(workers, int) or not 1 <= workers <= MAX_FAST_WORKERS:
        raise OpportunityError("P-C fast worker bound exceeded")
    if workers > 1 and fetcher is not None:
        raise OpportunityError("parallel P-C acquisition requires isolated default fetchers")

    def acquire(entry: dict) -> dict:
        return acquire_period(
            root,
            entry,
            fetcher=fetcher,
            plan_doc=population_plan,
            inventory=inventory,
            retrieved_ms=retrieved_ms,
            allow_daily_fallback=allow_daily_fallback,
            verified_binding=_bound_entry_from_verified_plan(population_plan, entry),
        )

    if workers == 1:
        candidates = [acquire(entry) for entry in entries]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            candidates = list(executor.map(acquire, entries))

    records = []
    for entry, candidate in zip(entries, candidates):
        record = _validate_ledger(root, population_plan, inventory, entry)
        if record.get("record_sha256") != candidate.get("record_sha256"):
            raise OpportunityError("P-C acquired ledger verification mismatch")
        records.append(record)
    return records


def _persist_batch(
    root: Path,
    population_plan: dict,
    records: list[dict],
    *,
    requested_limit: int,
    broad_continuation: bool,
) -> dict:
    batch_base = dict(
        schema="AF-01C-PC-BATCH/1",
        state="P_C_BROAD_BATCH_COMPLETE" if broad_continuation else "P_C_CANARY_BATCH_COMPLETE",
        plan_sha256=population_plan["plan_sha256"],
        requested_limit=requested_limit,
        acquired_count=len(records),
        identities=tuple(record["identity"] for record in records),
        records=tuple(record["record_sha256"] for record in records),
        state_counts=dict(sorted(Counter(record["state"] for record in records).items())),
    )
    batch_sha = digest(batch_base)
    batch_ref = f"batches/batch-{batch_sha}.json"
    save_artifact(root, batch_ref, canonical(batch_base))
    return batch_base | {
        "batch_sha256": batch_sha,
        "batch_ref": batch_ref,
    }


def acquire_batch(
    root: Path,
    plan_relative: str,
    inventory_relative: str,
    *,
    limit: int,
    storage_preflight_relative: str,
    continuation_acceptance_relative: str | None = None,
    allow_daily_fallback: bool = True,
    fetcher=None,
    retrieved_ms: int | None = None,
) -> dict:
    if not isinstance(limit, int) or not 1 <= limit <= MAX_CANARY_BATCH:
        raise OpportunityError("P-C canary batch limit exceeded")
    _verify_storage_preflight(root, storage_preflight_relative)
    population_plan, inventory = _load_bound_plan(root, plan_relative, inventory_relative)
    counts, completed, artifact_refs, artifact_bytes, missing = _scan_population(
        root,
        population_plan,
        inventory,
    )
    current_status = _status_from_verified_scan(
        population_plan,
        counts,
        completed,
        artifact_bytes,
    )
    broad_continuation = completed >= MAX_CANARY_BATCH
    if broad_continuation:
        if not continuation_acceptance_relative:
            raise OpportunityError("P-C canary population ceiling reached; continuation acceptance required")
        _verify_continuation_acceptance(
            root,
            continuation_acceptance_relative,
            population_plan,
            current_status,
        )

    missing = missing[:limit]
    if not broad_continuation:
        allowed = MAX_CANARY_BATCH - completed
        if len(missing) > allowed:
            missing = missing[:allowed]

    if retrieved_ms is None:
        retrieved_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    records = _acquire_verified_entries(
        root,
        population_plan,
        inventory,
        missing,
        allow_daily_fallback=allow_daily_fallback,
        fetcher=fetcher,
        retrieved_ms=retrieved_ms,
        workers=1,
    )

    for record in records:
        counts[record["state"]] += 1
    completed += len(records)
    artifact_bytes = _extend_artifact_accounting(
        root,
        artifact_refs,
        artifact_bytes,
        records,
    )

    batch = _persist_batch(
        root,
        population_plan,
        records,
        requested_limit=limit,
        broad_continuation=broad_continuation,
    )
    status = _status_from_verified_scan(
        population_plan,
        counts,
        completed,
        artifact_bytes,
    )
    return batch | {"population_status": status}


def acquire_batches_fast(
    root: Path,
    plan_relative: str,
    inventory_relative: str,
    *,
    limit: int,
    batch_count: int,
    workers: int,
    storage_preflight_relative: str,
    continuation_acceptance_relative: str | None = None,
    allow_daily_fallback: bool = True,
    fetcher=None,
    retrieved_ms: int | None = None,
) -> dict:
    """Run bounded internal batches after one verified restart scan.

    Progress is still derived from immutable ledgers: all pre-existing ledgers are
    verified once at process start and every newly written ledger is re-read and
    verified before it contributes to status.
    """
    if not isinstance(limit, int) or not 1 <= limit <= MAX_CANARY_BATCH:
        raise OpportunityError("P-C canary batch limit exceeded")
    if not isinstance(batch_count, int) or not 1 <= batch_count <= MAX_FAST_BATCHES:
        raise OpportunityError("P-C fast batch-count bound exceeded")
    if not isinstance(workers, int) or not 1 <= workers <= MAX_FAST_WORKERS:
        raise OpportunityError("P-C fast worker bound exceeded")
    if workers > 1 and fetcher is not None:
        raise OpportunityError("parallel P-C acquisition requires isolated default fetchers")

    _verify_storage_preflight(root, storage_preflight_relative)
    population_plan, inventory = _load_bound_plan(root, plan_relative, inventory_relative)
    counts, completed, artifact_refs, artifact_bytes, missing = _scan_population(
        root,
        population_plan,
        inventory,
    )
    current_status = _status_from_verified_scan(
        population_plan,
        counts,
        completed,
        artifact_bytes,
    )
    broad_continuation = completed >= MAX_CANARY_BATCH
    if broad_continuation:
        if not continuation_acceptance_relative:
            raise OpportunityError("P-C canary population ceiling reached; continuation acceptance required")
        _verify_continuation_acceptance(
            root,
            continuation_acceptance_relative,
            population_plan,
            current_status,
        )

    batch_summaries = []
    for _ in range(batch_count):
        if not missing:
            break

        batch_limit = min(limit, len(missing))
        if not broad_continuation:
            allowed = MAX_CANARY_BATCH - completed
            if allowed <= 0:
                break
            batch_limit = min(batch_limit, allowed)

        entries = missing[:batch_limit]
        batch_retrieved_ms = (
            retrieved_ms
            if retrieved_ms is not None
            else int(datetime.now(timezone.utc).timestamp() * 1000)
        )
        records = _acquire_verified_entries(
            root,
            population_plan,
            inventory,
            entries,
            allow_daily_fallback=allow_daily_fallback,
            fetcher=fetcher,
            retrieved_ms=batch_retrieved_ms,
            workers=workers,
        )

        for record in records:
            counts[record["state"]] += 1
        completed += len(records)
        artifact_bytes = _extend_artifact_accounting(
            root,
            artifact_refs,
            artifact_bytes,
            records,
        )

        batch = _persist_batch(
            root,
            population_plan,
            records,
            requested_limit=batch_limit,
            broad_continuation=broad_continuation,
        )
        batch_summaries.append(
            dict(
                batch_ref=batch["batch_ref"],
                batch_sha256=batch["batch_sha256"],
                acquired_count=batch["acquired_count"],
                state_counts=batch["state_counts"],
            )
        )
        del missing[:batch_limit]

        if not broad_continuation and completed >= MAX_CANARY_BATCH:
            break

    status = _status_from_verified_scan(
        population_plan,
        counts,
        completed,
        artifact_bytes,
    )
    run_base = dict(
        schema="AF-01C-PC-FAST-RUN/1",
        state="P_C_FAST_RUN_COMPLETE",
        plan_sha256=population_plan["plan_sha256"],
        requested_batch_count=batch_count,
        completed_batch_count=len(batch_summaries),
        per_batch_limit=limit,
        workers=workers,
        batches=tuple(batch_summaries),
        final_status_sha256=status["status_sha256"],
    )
    run_sha = digest(run_base)
    run_ref = f"runs/fast-run-{run_sha}.json"
    save_artifact(root, run_ref, canonical(run_base))
    return run_base | {
        "fast_run_sha256": run_sha,
        "fast_run_ref": run_ref,
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
