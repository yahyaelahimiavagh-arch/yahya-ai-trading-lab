"""Deterministic distributed-execution foundation for MCF-PROD-001.

This module defines portable batch/micro-shard identities, crash-safe content-
addressed result storage, pause/resume markers, reconciliation, and a local
SQLite coordinator registry. It deliberately exposes no production performance
execution command; the 6,852-candidate run remains Director-locked.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Mapping, Sequence

from .models import MCFError, canonical, digest, guard_root, safe_path, write_once
from .production_generator import freeze_executable_generation
from .production_rules import BLOCKED_FAMILIES
from .production_result_projection import storage_result

SCHEMA = "MCF_DISTRIBUTED_EXECUTION_PLAN/1.0.0"
RESULT_SCHEMA = "MCF_DISTRIBUTED_CANDIDATE_RESULT/1.0.0"
BATCH_MANIFEST_SCHEMA = "MCF_DISTRIBUTED_BATCH_RESULT_MANIFEST/1.0.0"
COORDINATOR_SCHEMA = "MCF_DISTRIBUTED_COORDINATOR/1.0.0"
GENERATION_ID = "MCF-PROD-001"
EXPECTED_EXECUTABLE_COUNT = 6852
LOGICAL_BATCH_SIZE = 500
MICROSHARD_SIZE = 25
BATCH_RE = re.compile(r"^B\d{3}$")
NODE_RE = re.compile(r"^NODE-[A-Z0-9][A-Z0-9_-]{1,31}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

SAFETY = {
    "paper_research_only": True,
    "live_master_lock": "OFF",
    "futures": False,
    "leverage": False,
    "short": False,
    "live": False,
    "order_endpoint": False,
    "ai_direct_execution": False,
    "fresh_oos_read": False,
    "recent_reserve_read": False,
    "p10_read": False,
    "p10_write": False,
    "p11_locked": True,
    "performance_execution_authorized": False,
}


def _sha(value: object) -> bool:
    return isinstance(value, str) and bool(SHA_RE.fullmatch(value))


def _node(value: str) -> str:
    if not isinstance(value, str) or not NODE_RE.fullmatch(value):
        raise MCFError("invalid distributed node id")
    return value


def _atomic_replace(path: Path, payload: bytes) -> None:
    guard_root(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".partial-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def build_execution_plan(executable_freeze: Mapping[str, object] | None = None) -> dict:
    """Freeze 6,852 candidates into 14 logical batches and 25-candidate micro-shards."""
    freeze = dict(executable_freeze or freeze_executable_generation(BLOCKED_FAMILIES))
    summary = freeze.get("summary")
    executable = tuple(freeze.get("executable", ()))
    if (
        not isinstance(summary, Mapping)
        or summary.get("generation_id") != GENERATION_ID
        or summary.get("state") != "PRE_OUTCOME_EXECUTABLE_SET_FROZEN"
        or summary.get("executable_candidate_count") != EXPECTED_EXECUTABLE_COUNT
        or len(executable) != EXPECTED_EXECUTABLE_COUNT
    ):
        raise MCFError("distributed plan requires exact frozen executable generation")
    rows = sorted(executable, key=lambda row: str(row["candidate_id"]))
    identities = []
    seen = set()
    for row in rows:
        cid = str(row.get("candidate_id", ""))
        spec = str(row.get("candidate_spec_sha256", ""))
        if not cid.startswith("MCF-PROD-001-") or cid in seen or not _sha(spec):
            raise MCFError("invalid/duplicate frozen candidate identity")
        seen.add(cid)
        identities.append({
            "candidate_id": cid,
            "candidate_spec_sha256": spec,
            "family": str(row["family"]),
            "timeframe": str(row["timeframe"]),
        })

    batches = []
    for batch_offset in range(0, len(identities), LOGICAL_BATCH_SIZE):
        batch_rows = identities[batch_offset:batch_offset + LOGICAL_BATCH_SIZE]
        batch_code = f"B{len(batches) + 1:03d}"
        microshards = []
        for shard_offset in range(0, len(batch_rows), MICROSHARD_SIZE):
            shard_rows = batch_rows[shard_offset:shard_offset + MICROSHARD_SIZE]
            shard_code = f"{batch_code}-S{len(microshards) + 1:03d}"
            shard_base = {
                "microshard_code": shard_code,
                "candidate_count": len(shard_rows),
                "candidates": shard_rows,
            }
            microshards.append({**shard_base, "microshard_sha256": digest(shard_base)})
        batch_base = {
            "batch_code": batch_code,
            "candidate_count": len(batch_rows),
            "first_candidate_id": batch_rows[0]["candidate_id"],
            "last_candidate_id": batch_rows[-1]["candidate_id"],
            "microshards": microshards,
        }
        batches.append({**batch_base, "batch_sha256": digest(batch_base)})

    if len(batches) != 14 or any(x["candidate_count"] != 500 for x in batches[:-1]) or batches[-1]["candidate_count"] != 352:
        raise MCFError("unexpected logical batch partition")
    base = {
        "schema": SCHEMA,
        "generation_id": GENERATION_ID,
        "state": "DISTRIBUTED_PLAN_FROZEN_NO_PERFORMANCE",
        "executable_freeze_sha256": summary["freeze_sha256"],
        "candidate_ledger_sha256": summary["candidate_ledger_sha256"],
        "neighbor_graph_sha256": summary["neighbor_graph_sha256"],
        "candidate_count": len(identities),
        "logical_batch_size": LOGICAL_BATCH_SIZE,
        "microshard_size": MICROSHARD_SIZE,
        "batch_count": len(batches),
        "batches": batches,
        "safety": SAFETY,
    }
    return {**base, "plan_sha256": digest(base)}


def validate_plan(plan: Mapping[str, object]) -> None:
    base = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if (
        plan.get("schema") != SCHEMA
        or plan.get("generation_id") != GENERATION_ID
        or plan.get("state") != "DISTRIBUTED_PLAN_FROZEN_NO_PERFORMANCE"
        or plan.get("candidate_count") != EXPECTED_EXECUTABLE_COUNT
        or plan.get("batch_count") != 14
        or plan.get("logical_batch_size") != LOGICAL_BATCH_SIZE
        or plan.get("microshard_size") != MICROSHARD_SIZE
        or plan.get("safety") != SAFETY
        or digest(base) != plan.get("plan_sha256")
    ):
        raise MCFError("distributed execution plan boundary mismatch")
    candidates = []
    for index, batch in enumerate(plan.get("batches", ()), 1):
        expected_code = f"B{index:03d}"
        if batch.get("batch_code") != expected_code or not BATCH_RE.fullmatch(expected_code):
            raise MCFError("distributed batch code mismatch")
        batch_base = {k: v for k, v in batch.items() if k != "batch_sha256"}
        if digest(batch_base) != batch.get("batch_sha256"):
            raise MCFError("distributed batch hash mismatch")
        local = []
        for shard_index, shard in enumerate(batch.get("microshards", ()), 1):
            if shard.get("microshard_code") != f"{expected_code}-S{shard_index:03d}":
                raise MCFError("distributed microshard code mismatch")
            shard_base = {k: v for k, v in shard.items() if k != "microshard_sha256"}
            if digest(shard_base) != shard.get("microshard_sha256"):
                raise MCFError("distributed microshard hash mismatch")
            if shard.get("candidate_count") != len(shard.get("candidates", ())):
                raise MCFError("distributed microshard count mismatch")
            local.extend(shard["candidates"])
        if batch.get("candidate_count") != len(local):
            raise MCFError("distributed batch count mismatch")
        if not local or local[0]["candidate_id"] != batch.get("first_candidate_id") or local[-1]["candidate_id"] != batch.get("last_candidate_id"):
            raise MCFError("distributed batch boundary mismatch")
        candidates.extend(local)
    ids = [x["candidate_id"] for x in candidates]
    if len(ids) != EXPECTED_EXECUTABLE_COUNT or len(set(ids)) != len(ids) or ids != sorted(ids):
        raise MCFError("distributed plan candidate coverage mismatch")


def batch(plan: Mapping[str, object], batch_code: str) -> Mapping[str, object]:
    validate_plan(plan)
    if not isinstance(batch_code, str) or not BATCH_RE.fullmatch(batch_code):
        raise MCFError("invalid batch code")
    found = next((x for x in plan["batches"] if x["batch_code"] == batch_code), None)
    if found is None:
        raise MCFError("batch not in frozen distributed plan")
    return found


def batch_candidates(plan: Mapping[str, object], batch_code: str) -> tuple[Mapping[str, object], ...]:
    item = batch(plan, batch_code)
    return tuple(candidate for shard in item["microshards"] for candidate in shard["candidates"])


def pause_path(root: Path, batch_code: str) -> Path:
    return safe_path(root, f"control/{batch_code}.pause")


def request_pause(root: Path, plan: Mapping[str, object], batch_code: str) -> dict:
    batch(plan, batch_code)
    target = pause_path(root, batch_code)
    write_once(target, canonical({"batch_code": batch_code, "state": "PAUSE_REQUESTED"}))
    return {"batch_code": batch_code, "status": "PAUSE_REQUESTED"}


def clear_pause(root: Path, plan: Mapping[str, object], batch_code: str) -> dict:
    batch(plan, batch_code)
    target = pause_path(root, batch_code)
    if target.exists():
        if target.is_symlink():
            raise MCFError("pause marker symlink")
        target.unlink()
    return {"batch_code": batch_code, "status": "RESUME_ALLOWED"}


def pause_requested(root: Path, plan: Mapping[str, object], batch_code: str) -> bool:
    batch(plan, batch_code)
    target = pause_path(root, batch_code)
    return target.is_file()


def _candidate_result_dir(root: Path, batch_code: str, candidate_id: str) -> Path:
    return safe_path(root, f"results/{batch_code}/{candidate_id}")


def write_candidate_result(
    root: Path,
    plan: Mapping[str, object],
    batch_code: str,
    candidate_id: str,
    *,
    node_id: str,
    git_sha: str,
    runner_input_sha256: str,
    result: Mapping[str, object],
) -> dict:
    """Persist one immutable candidate result; identical reruns are idempotent."""
    _node(node_id)
    if not _sha(git_sha) or not _sha(runner_input_sha256):
        raise MCFError("candidate result requires pinned git/runner identities")
    expected = {x["candidate_id"]: x for x in batch_candidates(plan, batch_code)}
    row = expected.get(candidate_id)
    if row is None:
        raise MCFError("candidate outside requested batch")
    compact = storage_result(result)
    if compact.get("candidate_id") != candidate_id or compact.get("candidate_spec_sha256") != row["candidate_spec_sha256"]:
        raise MCFError("candidate result identity mismatch")
    identity = {
        "schema": RESULT_SCHEMA,
        "generation_id": GENERATION_ID,
        "plan_sha256": plan["plan_sha256"],
        "batch_code": batch_code,
        "candidate_id": candidate_id,
        "candidate_spec_sha256": row["candidate_spec_sha256"],
        "git_sha": git_sha,
        "runner_input_sha256": runner_input_sha256,
        "result": compact,
    }
    # Compute location must not change scientific artifact identity.
    doc = {
        **identity,
        "producer_node_id": node_id,
        "result_artifact_sha256": digest(identity),
    }
    directory = _candidate_result_dir(root, batch_code, candidate_id)
    directory.mkdir(parents=True, exist_ok=True)
    target = safe_path(root, f"results/{batch_code}/{candidate_id}/result-{doc['result_artifact_sha256']}.json")
    existing = sorted(directory.glob("result-*.json"))
    for path in existing:
        if path.is_symlink():
            raise MCFError("candidate result symlink")
        old = json.loads(path.read_text())
        old_identity = {
            k: v for k, v in old.items()
            if k not in {"result_artifact_sha256", "producer_node_id"}
        }
        if digest(old_identity) != old.get("result_artifact_sha256"):
            raise MCFError("existing candidate result artifact identity invalid")
        if old.get("result_artifact_sha256") != doc["result_artifact_sha256"]:
            raise MCFError("nondeterministic duplicate candidate result")
        # An identical rerun on another node is scientifically idempotent.
        return {
            "batch_code": batch_code,
            "candidate_id": candidate_id,
            "result_artifact_sha256": old["result_artifact_sha256"],
            "artifact": str(path.relative_to(guard_root(root))),
        }
    write_once(target, canonical(doc))
    return {
        "batch_code": batch_code,
        "candidate_id": candidate_id,
        "result_artifact_sha256": doc["result_artifact_sha256"],
        "artifact": str(target.relative_to(guard_root(root))),
    }


def _read_candidate_result(root: Path, plan: Mapping[str, object], batch_code: str,
                           expected: Mapping[str, object]) -> dict | None:
    directory = _candidate_result_dir(root, batch_code, expected["candidate_id"])
    if not directory.exists():
        return None
    paths = sorted(directory.glob("result-*.json"))
    if not paths:
        return None
    if len(paths) != 1:
        raise MCFError("duplicate result artifacts for candidate")
    raw = paths[0].read_bytes()
    doc = json.loads(raw)
    identity = {
        k: v for k, v in doc.items()
        if k not in {"result_artifact_sha256", "producer_node_id"}
    }
    if (
        canonical(doc) != raw
        or doc.get("schema") != RESULT_SCHEMA
        or doc.get("generation_id") != GENERATION_ID
        or doc.get("plan_sha256") != plan["plan_sha256"]
        or doc.get("batch_code") != batch_code
        or doc.get("candidate_id") != expected["candidate_id"]
        or doc.get("candidate_spec_sha256") != expected["candidate_spec_sha256"]
        or not _sha(doc.get("git_sha"))
        or not _sha(doc.get("runner_input_sha256"))
        or not NODE_RE.fullmatch(str(doc.get("producer_node_id", "")))
        or digest(identity) != doc.get("result_artifact_sha256")
    ):
        raise MCFError("candidate result artifact boundary mismatch")
    result = doc.get("result")
    if not isinstance(result, Mapping) or result.get("candidate_id") != expected["candidate_id"] or result.get("candidate_spec_sha256") != expected["candidate_spec_sha256"]:
        raise MCFError("embedded candidate result identity mismatch")
    return doc


def status(root: Path, plan: Mapping[str, object], batch_code: str) -> dict:
    rows = batch_candidates(plan, batch_code)
    complete = []
    identities = set()
    nodes = set()
    git_shas = set()
    runner_shas = set()
    for row in rows:
        doc = _read_candidate_result(root, plan, batch_code, row)
        if doc is None:
            continue
        if doc["candidate_id"] in identities:
            raise MCFError("duplicate completed candidate identity")
        identities.add(doc["candidate_id"])
        complete.append(doc["candidate_id"])
        nodes.add(doc["producer_node_id"])
        git_shas.add(doc["git_sha"])
        runner_shas.add(doc["runner_input_sha256"])
    pending = [row["candidate_id"] for row in rows if row["candidate_id"] not in identities]
    paused = pause_requested(root, plan, batch_code)
    state = "COMPLETE" if not pending else ("PAUSED_SAFE" if paused else "READY_OR_RUNNING")
    return {
        "batch_code": batch_code,
        "status": state,
        "total": len(rows),
        "complete": len(complete),
        "remaining": len(pending),
        "next_candidate_id": None if not pending else pending[0],
        "nodes": sorted(nodes),
        "git_shas": sorted(git_shas),
        "runner_input_sha256s": sorted(runner_shas),
        "pause_requested": paused,
    }


def next_candidate(root: Path, plan: Mapping[str, object], batch_code: str) -> Mapping[str, object] | None:
    if pause_requested(root, plan, batch_code):
        return None
    completed = set()
    rows = batch_candidates(plan, batch_code)
    for row in rows:
        if _read_candidate_result(root, plan, batch_code, row) is not None:
            completed.add(row["candidate_id"])
    return next((row for row in rows if row["candidate_id"] not in completed), None)


def build_batch_manifest(root: Path, plan: Mapping[str, object], batch_code: str) -> dict:
    rows = batch_candidates(plan, batch_code)
    artifacts = []
    git_shas = set()
    runner_shas = set()
    nodes = set()
    for row in rows:
        doc = _read_candidate_result(root, plan, batch_code, row)
        if doc is None:
            raise MCFError("batch result manifest requires complete batch")
        artifacts.append({
            "candidate_id": row["candidate_id"],
            "candidate_spec_sha256": row["candidate_spec_sha256"],
            "result_artifact_sha256": doc["result_artifact_sha256"],
        })
        git_shas.add(doc["git_sha"])
        runner_shas.add(doc["runner_input_sha256"])
        nodes.add(doc["producer_node_id"])
    if len(git_shas) != 1 or len(runner_shas) != 1:
        raise MCFError("batch mixes git or runner-input identities")
    base = {
        "schema": BATCH_MANIFEST_SCHEMA,
        "generation_id": GENERATION_ID,
        "plan_sha256": plan["plan_sha256"],
        "batch_code": batch_code,
        "batch_sha256": batch(plan, batch_code)["batch_sha256"],
        "candidate_count": len(rows),
        "git_sha": next(iter(git_shas)),
        "runner_input_sha256": next(iter(runner_shas)),
        "nodes": sorted(nodes),
        "artifacts": artifacts,
    }
    return {**base, "batch_result_manifest_sha256": digest(base)}


def validate_batch_manifest_structure(plan: Mapping[str, object], manifest: Mapping[str, object]) -> None:
    """Validate a complete batch manifest without trusting worker-local files."""
    batch_code = str(manifest.get("batch_code", ""))
    frozen = batch(plan, batch_code)
    expected = batch_candidates(plan, batch_code)
    base = {k: v for k, v in manifest.items() if k != "batch_result_manifest_sha256"}
    artifacts = manifest.get("artifacts")
    if (
        manifest.get("schema") != BATCH_MANIFEST_SCHEMA
        or manifest.get("generation_id") != GENERATION_ID
        or manifest.get("plan_sha256") != plan["plan_sha256"]
        or manifest.get("batch_sha256") != frozen["batch_sha256"]
        or manifest.get("candidate_count") != frozen["candidate_count"]
        or not _sha(manifest.get("git_sha"))
        or not _sha(manifest.get("runner_input_sha256"))
        or not isinstance(manifest.get("nodes"), list)
        or not manifest.get("nodes")
        or any(not isinstance(node, str) or not NODE_RE.fullmatch(node) for node in manifest["nodes"])
        or manifest["nodes"] != sorted(set(manifest["nodes"]))
        or not isinstance(artifacts, list)
        or len(artifacts) != len(expected)
        or digest(base) != manifest.get("batch_result_manifest_sha256")
    ):
        raise MCFError("batch result manifest boundary mismatch")
    for want, got in zip(expected, artifacts):
        if (
            not isinstance(got, Mapping)
            or got.get("candidate_id") != want["candidate_id"]
            or got.get("candidate_spec_sha256") != want["candidate_spec_sha256"]
            or not _sha(got.get("result_artifact_sha256"))
        ):
            raise MCFError("batch result manifest candidate coverage mismatch")


def verify_batch_manifest(root: Path, plan: Mapping[str, object], manifest: Mapping[str, object]) -> dict:
    batch_code = str(manifest.get("batch_code", ""))
    validate_batch_manifest_structure(plan, manifest)
    rebuilt = build_batch_manifest(root, plan, batch_code)
    if rebuilt != dict(manifest):
        raise MCFError("batch result manifest does not reconcile to artifacts")
    return {
        "status": "BATCH_RECONCILED_READY_FOR_INGEST",
        "batch_code": batch_code,
        "candidate_count": manifest["candidate_count"],
        "batch_result_manifest_sha256": manifest["batch_result_manifest_sha256"],
    }


def init_coordinator(db_path: Path, plan: Mapping[str, object]) -> dict:
    validate_plan(plan)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS batches (
            batch_code TEXT PRIMARY KEY,
            batch_sha256 TEXT NOT NULL,
            state TEXT NOT NULL,
            owner_node TEXT,
            lease_until_ms INTEGER,
            updated_at_ms INTEGER NOT NULL,
            ingested_manifest_sha256 TEXT
        )""")
        existing = dict(con.execute("SELECT key,value FROM meta"))
        if existing and existing.get("plan_sha256") != plan["plan_sha256"]:
            raise MCFError("coordinator database bound to different distributed plan")
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema',?)", (COORDINATOR_SCHEMA,))
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('plan_sha256',?)", (plan["plan_sha256"],))
        now = int(time.time() * 1000)
        for item in plan["batches"]:
            con.execute(
                """INSERT OR IGNORE INTO batches
                (batch_code,batch_sha256,state,updated_at_ms)
                VALUES(?,?,?,?)""",
                (item["batch_code"], item["batch_sha256"], "AVAILABLE", now),
            )
        con.commit()
    return {"status": "COORDINATOR_READY", "plan_sha256": plan["plan_sha256"], "batch_count": 14}


def _coordinator_bound(con: sqlite3.Connection, plan: Mapping[str, object]) -> None:
    validate_plan(plan)
    meta = dict(con.execute("SELECT key,value FROM meta"))
    if meta.get("schema") != COORDINATOR_SCHEMA or meta.get("plan_sha256") != plan["plan_sha256"]:
        raise MCFError("coordinator database binding mismatch")


def claim_batch(db_path: Path, plan: Mapping[str, object], *, node_id: str,
                batch_code: str | None = None, lease_seconds: int = 900,
                now_ms: int | None = None) -> dict:
    _node(node_id)
    if type(lease_seconds) is not int or not 60 <= lease_seconds <= 86400:
        raise MCFError("invalid coordinator lease")
    now = int(time.time() * 1000) if now_ms is None else int(now_ms)
    with sqlite3.connect(db_path, timeout=30, isolation_level=None) as con:
        con.execute("BEGIN IMMEDIATE")
        _coordinator_bound(con, plan)
        con.execute(
            """UPDATE batches SET state='AVAILABLE', owner_node=NULL, lease_until_ms=NULL,
               updated_at_ms=? WHERE state='CLAIMED' AND lease_until_ms < ?""",
            (now, now),
        )
        if batch_code is not None:
            batch(plan, batch_code)
            row = con.execute(
                "SELECT batch_code,state,owner_node,lease_until_ms FROM batches WHERE batch_code=?",
                (batch_code,),
            ).fetchone()
            if row is None:
                raise MCFError("coordinator missing frozen batch")
            if row[1] == "INGESTED":
                raise MCFError("batch already ingested")
            if row[1] == "CLAIMED" and row[2] != node_id and (row[3] or 0) >= now:
                raise MCFError("batch already claimed by another node")
            chosen = batch_code
        else:
            row = con.execute(
                """SELECT batch_code FROM batches
                   WHERE state='AVAILABLE' ORDER BY batch_code LIMIT 1"""
            ).fetchone()
            if row is None:
                raise MCFError("no available distributed batch")
            chosen = row[0]
        until = now + lease_seconds * 1000
        con.execute(
            """UPDATE batches SET state='CLAIMED', owner_node=?, lease_until_ms=?, updated_at_ms=?
               WHERE batch_code=?""",
            (node_id, until, now, chosen),
        )
        con.commit()
    return {"status": "BATCH_CLAIMED", "batch_code": chosen, "node_id": node_id, "lease_until_ms": until}


def heartbeat(db_path: Path, plan: Mapping[str, object], *, node_id: str,
              batch_code: str, lease_seconds: int = 900, now_ms: int | None = None) -> dict:
    _node(node_id)
    batch(plan, batch_code)
    now = int(time.time() * 1000) if now_ms is None else int(now_ms)
    with sqlite3.connect(db_path, timeout=30, isolation_level=None) as con:
        con.execute("BEGIN IMMEDIATE")
        _coordinator_bound(con, plan)
        row = con.execute(
            "SELECT state,owner_node,lease_until_ms FROM batches WHERE batch_code=?",
            (batch_code,),
        ).fetchone()
        if row is None or row[0] != "CLAIMED" or row[1] != node_id or (row[2] or 0) < now:
            raise MCFError("heartbeat requires active matching lease")
        until = now + lease_seconds * 1000
        con.execute(
            "UPDATE batches SET lease_until_ms=?,updated_at_ms=? WHERE batch_code=?",
            (until, now, batch_code),
        )
        con.commit()
    return {"status": "HEARTBEAT_ACCEPTED", "batch_code": batch_code, "node_id": node_id, "lease_until_ms": until}


def mark_ingested(db_path: Path, plan: Mapping[str, object], *, manifest: Mapping[str, object],
                  now_ms: int | None = None) -> dict:
    batch_code = str(manifest.get("batch_code", ""))
    validate_batch_manifest_structure(plan, manifest)
    manifest_sha = str(manifest["batch_result_manifest_sha256"])
    now = int(time.time() * 1000) if now_ms is None else int(now_ms)
    with sqlite3.connect(db_path, timeout=30, isolation_level=None) as con:
        con.execute("BEGIN IMMEDIATE")
        _coordinator_bound(con, plan)
        row = con.execute(
            "SELECT state,ingested_manifest_sha256 FROM batches WHERE batch_code=?",
            (batch_code,),
        ).fetchone()
        if row is None:
            raise MCFError("coordinator missing ingested batch")
        if row[0] == "INGESTED" and row[1] != manifest_sha:
            raise MCFError("conflicting ingested manifest")
        con.execute(
            """UPDATE batches SET state='INGESTED',owner_node=NULL,lease_until_ms=NULL,
               updated_at_ms=?,ingested_manifest_sha256=? WHERE batch_code=?""",
            (now, manifest_sha, batch_code),
        )
        con.commit()
    return {"status": "BATCH_INGESTED", "batch_code": batch_code, "batch_result_manifest_sha256": manifest_sha}


def coordinator_status(db_path: Path, plan: Mapping[str, object]) -> dict:
    with sqlite3.connect(db_path) as con:
        _coordinator_bound(con, plan)
        rows = con.execute(
            "SELECT batch_code,state,owner_node,lease_until_ms,ingested_manifest_sha256 FROM batches ORDER BY batch_code"
        ).fetchall()
    counts = {}
    for row in rows:
        counts[row[1]] = counts.get(row[1], 0) + 1
    return {
        "status": "COORDINATOR_STATUS",
        "plan_sha256": plan["plan_sha256"],
        "counts": counts,
        "batches": [
            {
                "batch_code": row[0],
                "state": row[1],
                "owner_node": row[2],
                "lease_until_ms": row[3],
                "ingested_manifest_sha256": row[4],
            }
            for row in rows
        ],
    }


def d1_seed_sql(plan: Mapping[str, object]) -> str:
    """Emit deterministic D1 seed SQL for plan metadata and 14 batch identities."""
    validate_plan(plan)
    statements = [
        "INSERT OR REPLACE INTO meta(key,value) VALUES('schema','MCF_DISTRIBUTED_COORDINATOR/1.0.0');",
        f"INSERT OR REPLACE INTO meta(key,value) VALUES('plan_sha256','{plan['plan_sha256']}');",
        f"INSERT OR REPLACE INTO meta(key,value) VALUES('generation_id','{GENERATION_ID}');",
        "DELETE FROM batches;",
    ]
    for item in plan["batches"]:
        statements.append(
            "INSERT INTO batches(batch_code,batch_sha256,plan_sha256,candidate_count,state,updated_at_ms) "
            f"VALUES('{item['batch_code']}','{item['batch_sha256']}','{plan['plan_sha256']}',"
            f"{item['candidate_count']},'AVAILABLE',0);"
        )
    return "\n".join(statements) + "\n"


def _load_plan(path: Path) -> dict:
    raw = path.read_bytes()
    plan = json.loads(raw)
    if canonical(plan) != raw:
        raise MCFError("plan file must be canonical")
    validate_plan(plan)
    return plan


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("freeze-plan")
    p.add_argument("--output", required=True, type=Path)

    p = sub.add_parser("status")
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--batch", required=True)

    for name in ("pause", "resume"):
        p = sub.add_parser(name)
        p.add_argument("--root", required=True, type=Path)
        p.add_argument("--plan", required=True, type=Path)
        p.add_argument("--batch", required=True)

    p = sub.add_parser("coordinator-init")
    p.add_argument("--db", required=True, type=Path)
    p.add_argument("--plan", required=True, type=Path)

    p = sub.add_parser("coordinator-status")
    p.add_argument("--db", required=True, type=Path)
    p.add_argument("--plan", required=True, type=Path)

    p = sub.add_parser("emit-d1-seed")
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "freeze-plan":
            plan = build_execution_plan()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if args.output.exists() and args.output.read_bytes() != canonical(plan):
                raise MCFError("distributed plan collision")
            args.output.write_bytes(canonical(plan))
            result = {
                "status": plan["state"],
                "plan_sha256": plan["plan_sha256"],
                "candidate_count": plan["candidate_count"],
                "batch_count": plan["batch_count"],
                "performance_execution_authorized": False,
            }
        else:
            plan = _load_plan(args.plan)
            if args.command == "status":
                result = status(args.root, plan, args.batch)
            elif args.command == "pause":
                result = request_pause(args.root, plan, args.batch)
            elif args.command == "resume":
                result = clear_pause(args.root, plan, args.batch)
            elif args.command == "coordinator-init":
                result = init_coordinator(args.db, plan)
            elif args.command == "coordinator-status":
                result = coordinator_status(args.db, plan)
            elif args.command == "emit-d1-seed":
                payload = d1_seed_sql(plan).encode("utf-8")
                if args.output.exists() and args.output.read_bytes() != payload:
                    raise MCFError("D1 seed collision")
                _atomic_replace(args.output, payload)
                result = {
                    "status": "D1_SEED_EMITTED",
                    "plan_sha256": plan["plan_sha256"],
                    "batch_count": plan["batch_count"],
                    "output": str(args.output),
                }
            else:
                raise MCFError("unsupported distributed command")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({"status": "DISTRIBUTED_EXECUTION_BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
