"""SSH-only coordinator and result relay for distributed MCF workers.

This is the zero-new-service transport: worker nodes use OpenSSH to the existing
VPS. A dedicated forced-command SSH key maps to one fixed NODE-* identity, so
remote workers never receive a general VPS shell.

Control RPC and result transfer both travel over SSH port 22. No Cloudflare,
R2, D1, domain, public HTTP listener, or additional Python dependency is needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping, Sequence

from .models import MCFError, canonical, guard_root, safe_path, write_once
from .production_distributed import (
    BATCH_RE,
    NODE_RE,
    SHA_RE,
    batch_candidates,
    build_batch_manifest,
    claim_batch,
    coordinator_mark_paused,
    coordinator_pause_request,
    coordinator_release,
    coordinator_resume,
    coordinator_status,
    heartbeat,
    init_coordinator,
    mark_ingested,
    validate_batch_manifest_structure,
    validate_candidate_result_document,
    validate_plan,
    verify_batch_manifest,
)

BUNDLE_SCHEMA = "MCF_SSH_BATCH_TRANSFER/1.0.0"
MAX_BUNDLE_BYTES = 1024 * 1024 * 1024
MAX_HEADER_BYTES = 8 * 1024 * 1024
MAX_ARTIFACT_LINE_BYTES = 32 * 1024 * 1024
DEFAULT_LEASE_SECONDS = 7200


def _load_plan(path: Path) -> dict:
    raw = path.read_bytes()
    doc = json.loads(raw)
    if not isinstance(doc, dict) or canonical(doc) != raw:
        raise MCFError("SSH gateway plan must be canonical JSON")
    validate_plan(doc)
    return doc


def _file_sha256(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def build_batch_bundle(
    root: Path,
    plan: Mapping[str, object],
    batch_code: str,
    output_root: Path,
) -> dict:
    """Build one immutable JSONL transfer bundle from a complete verified batch."""
    validate_plan(plan)
    manifest = build_batch_manifest(root, plan, batch_code)
    verify_batch_manifest(root, plan, manifest)
    output_root.mkdir(parents=True, exist_ok=True)
    guard_root(output_root)

    header = {
        "schema": BUNDLE_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "batch_code": batch_code,
        "candidate_count": manifest["candidate_count"],
        "batch_result_manifest_sha256": manifest["batch_result_manifest_sha256"],
        "manifest": manifest,
    }

    fd, tmp_name = tempfile.mkstemp(prefix=".partial-bundle-", dir=output_root)
    tmp = Path(tmp_name)
    h = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(fd, "wb") as handle:
            first = canonical(header)
            handle.write(first)
            h.update(first)
            total += len(first)
            for row in manifest["artifacts"]:
                relative = (
                    f"results/{batch_code}/{row['candidate_id']}/"
                    f"result-{row['result_artifact_sha256']}.json"
                )
                raw = safe_path(root, relative).read_bytes()
                doc = json.loads(raw)
                validate_candidate_result_document(plan, batch_code, row, doc, raw=raw)
                if doc.get("result_artifact_sha256") != row["result_artifact_sha256"]:
                    raise MCFError("bundle artifact/manifest SHA mismatch")
                handle.write(raw)
                h.update(raw)
                total += len(raw)
                if total > MAX_BUNDLE_BYTES:
                    raise MCFError("SSH batch bundle exceeds bounded transfer size")
            handle.flush()
            os.fsync(handle.fileno())

        raw_sha = h.hexdigest()
        relative = (
            f"bundles/{batch_code}/bundle-"
            f"{manifest['batch_result_manifest_sha256']}-{raw_sha}.jsonl"
        )
        target = safe_path(output_root, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(tmp, target)
        except FileExistsError:
            if target.is_symlink() or target.read_bytes() != tmp.read_bytes():
                raise MCFError("SSH bundle identity collision")
        return {
            "status": "SSH_BATCH_BUNDLE_READY_NO_TRANSFER",
            "batch_code": batch_code,
            "candidate_count": manifest["candidate_count"],
            "batch_result_manifest_sha256": manifest["batch_result_manifest_sha256"],
            "bundle_sha256": raw_sha,
            "bundle_bytes": total,
            "bundle_path": str(target),
        }
    finally:
        if tmp.exists():
            tmp.unlink()


def ingest_batch_bundle(
    bundle_path: Path,
    *,
    results_root: Path,
    plan: Mapping[str, object],
    coordinator_db: Path,
    uploader_node_id: str,
) -> dict:
    """Verify a received bundle before writing immutable candidate artifacts."""
    validate_plan(plan)
    if not NODE_RE.fullmatch(uploader_node_id):
        raise MCFError("invalid SSH uploader node")
    results_root.mkdir(parents=True, exist_ok=True)
    guard_root(results_root)

    bundle_sha, bundle_bytes = _file_sha256(bundle_path)
    if bundle_bytes < 1 or bundle_bytes > MAX_BUNDLE_BYTES:
        raise MCFError("SSH batch bundle size outside bounded range")

    with bundle_path.open("rb") as handle:
        header_raw = handle.readline(MAX_HEADER_BYTES + 1)
        if not header_raw or len(header_raw) > MAX_HEADER_BYTES:
            raise MCFError("SSH batch bundle header exceeds bound")
        header = json.loads(header_raw)
        if not isinstance(header, dict) or canonical(header) != header_raw:
            raise MCFError("SSH batch bundle header is not canonical")

        manifest = header.get("manifest")
        if not isinstance(manifest, Mapping):
            raise MCFError("SSH batch bundle missing manifest")
        batch_code = str(header.get("batch_code", ""))
        validate_batch_manifest_structure(plan, manifest)
        if (
            header.get("schema") != BUNDLE_SCHEMA
            or header.get("plan_sha256") != plan["plan_sha256"]
            or manifest.get("batch_code") != batch_code
            or header.get("candidate_count") != manifest.get("candidate_count")
            or header.get("batch_result_manifest_sha256")
            != manifest.get("batch_result_manifest_sha256")
        ):
            raise MCFError("SSH batch bundle boundary mismatch")

        expected_rows = list(manifest["artifacts"])
        for row in expected_rows:
            raw = handle.readline(MAX_ARTIFACT_LINE_BYTES + 1)
            if not raw or len(raw) > MAX_ARTIFACT_LINE_BYTES:
                raise MCFError("SSH candidate artifact line missing or oversized")
            doc = json.loads(raw)
            if not isinstance(doc, Mapping):
                raise MCFError("SSH candidate artifact must be JSON object")
            validate_candidate_result_document(plan, batch_code, row, doc, raw=raw)
            if doc.get("result_artifact_sha256") != row["result_artifact_sha256"]:
                raise MCFError("SSH candidate artifact SHA differs from manifest")
            relative = (
                f"results/{batch_code}/{row['candidate_id']}/"
                f"result-{row['result_artifact_sha256']}.json"
            )
            write_once(safe_path(results_root, relative), raw)

        if handle.read(1) != b"":
            raise MCFError("SSH batch bundle has unexpected trailing content")

    verified = verify_batch_manifest(results_root, plan, manifest)
    accepted = mark_ingested(coordinator_db, plan, manifest=manifest)
    receipt = {
        "schema": "MCF_SSH_INGEST_RECEIPT/1.0.0",
        "status": "SSH_BATCH_INGESTED_ACCEPTED",
        "plan_sha256": plan["plan_sha256"],
        "batch_code": batch_code,
        "batch_result_manifest_sha256": manifest["batch_result_manifest_sha256"],
        "candidate_count": verified["candidate_count"],
        "bundle_sha256": bundle_sha,
        "bundle_bytes": bundle_bytes,
        "uploader_node_id": uploader_node_id,
    }
    receipt_path = safe_path(
        results_root,
        f"receipts/{batch_code}/receipt-"
        f"{manifest['batch_result_manifest_sha256']}-{bundle_sha}.json",
    )
    write_once(receipt_path, canonical(receipt))
    return {**receipt, "coordinator_status": accepted["status"]}


def _receive_stdin(
    spool_root: Path,
    *,
    node_id: str,
    batch_code: str,
    manifest_sha256: str,
    expected_bytes: int,
    expected_sha256: str,
) -> Path:
    if (
        not NODE_RE.fullmatch(node_id)
        or not BATCH_RE.fullmatch(batch_code)
        or not SHA_RE.fullmatch(manifest_sha256)
        or not SHA_RE.fullmatch(expected_sha256)
        or not 1 <= expected_bytes <= MAX_BUNDLE_BYTES
    ):
        raise MCFError("invalid SSH upload metadata")
    spool_root.mkdir(parents=True, exist_ok=True)
    guard_root(spool_root)
    relative = (
        f"{node_id}/{batch_code}/incoming-"
        f"{manifest_sha256}-{expected_sha256}.jsonl"
    )
    target = safe_path(spool_root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        actual_sha, actual_bytes = _file_sha256(target)
        if actual_sha != expected_sha256 or actual_bytes != expected_bytes:
            raise MCFError("existing SSH spool artifact collision")
        return target

    fd, tmp_name = tempfile.mkstemp(prefix=".partial-upload-", dir=target.parent)
    tmp = Path(tmp_name)
    h = hashlib.sha256()
    remaining = expected_bytes
    try:
        with os.fdopen(fd, "wb") as handle:
            while remaining:
                chunk = sys.stdin.buffer.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise MCFError("SSH upload ended before declared byte count")
                handle.write(chunk)
                h.update(chunk)
                remaining -= len(chunk)
            if sys.stdin.buffer.read(1) != b"":
                raise MCFError("SSH upload contains bytes beyond declared size")
            handle.flush()
            os.fsync(handle.fileno())
        if h.hexdigest() != expected_sha256:
            raise MCFError("SSH upload raw SHA mismatch")
        try:
            os.link(tmp, target)
        except FileExistsError:
            actual_sha, actual_bytes = _file_sha256(target)
            if actual_sha != expected_sha256 or actual_bytes != expected_bytes:
                raise MCFError("concurrent SSH spool collision")
        return target
    finally:
        if tmp.exists():
            tmp.unlink()


def _owned_batch(db: Path, plan: Mapping[str, object], batch_code: str, node_id: str) -> None:
    report = coordinator_status(db, plan)
    row = next((x for x in report["batches"] if x["batch_code"] == batch_code), None)
    if row is None or row.get("owner_node") != node_id or row.get("state") not in {
        "CLAIMED", "PAUSE_REQUESTED", "PAUSED"
    }:
        raise MCFError("SSH upload requires matching coordinator batch owner")


def execute_server_command(
    command: str,
    *,
    node_id: str,
    plan: Mapping[str, object],
    db: Path,
    results_root: Path,
    spool_root: Path,
) -> dict:
    if not NODE_RE.fullmatch(node_id):
        raise MCFError("invalid forced-command node id")
    init_coordinator(db, plan)
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise MCFError("invalid SSH command syntax") from exc
    if not parts:
        raise MCFError("empty SSH gateway command")
    op, args = parts[0], parts[1:]

    if op == "status" and not args:
        return coordinator_status(db, plan)
    if op == "claim" and len(args) in {0, 1, 2}:
        batch_code = None if not args else args[0]
        lease = DEFAULT_LEASE_SECONDS if len(args) < 2 else int(args[1])
        return claim_batch(db, plan, node_id=node_id, batch_code=batch_code, lease_seconds=lease)
    if op == "heartbeat" and len(args) in {1, 2}:
        lease = DEFAULT_LEASE_SECONDS if len(args) == 1 else int(args[1])
        return heartbeat(db, plan, node_id=node_id, batch_code=args[0], lease_seconds=lease)
    if op == "pause-request" and len(args) == 1:
        return coordinator_pause_request(db, plan, node_id=node_id, batch_code=args[0])
    if op == "paused" and len(args) == 1:
        return coordinator_mark_paused(db, plan, node_id=node_id, batch_code=args[0])
    if op == "resume" and len(args) in {1, 2}:
        lease = DEFAULT_LEASE_SECONDS if len(args) == 1 else int(args[1])
        return coordinator_resume(db, plan, node_id=node_id, batch_code=args[0], lease_seconds=lease)
    if op == "release" and len(args) == 1:
        return coordinator_release(db, plan, node_id=node_id, batch_code=args[0])
    if op == "upload" and len(args) == 4:
        batch_code, manifest_sha, byte_text, raw_sha = args
        expected_bytes = int(byte_text)
        _owned_batch(db, plan, batch_code, node_id)
        spool = _receive_stdin(
            spool_root,
            node_id=node_id,
            batch_code=batch_code,
            manifest_sha256=manifest_sha,
            expected_bytes=expected_bytes,
            expected_sha256=raw_sha,
        )
        result = ingest_batch_bundle(
            spool,
            results_root=results_root,
            plan=plan,
            coordinator_db=db,
            uploader_node_id=node_id,
        )
        if result["batch_result_manifest_sha256"] != manifest_sha:
            raise MCFError("SSH upload declared manifest SHA mismatch")
        try:
            spool.unlink()
        except OSError:
            pass
        return result

    raise MCFError("SSH gateway command is not allowed")


def ssh_request(
    *,
    host: str,
    user: str,
    identity_file: Path,
    known_hosts: Path,
    remote_args: Sequence[str],
    port: int = 22,
    payload_path: Path | None = None,
    timeout: int = 120,
) -> dict:
    if not host or not user or not remote_args or not 1 <= port <= 65535:
        raise MCFError("invalid SSH client configuration")
    if not identity_file.is_file() or not known_hosts.is_file():
        raise MCFError("SSH identity/known_hosts file missing")
    for arg in remote_args:
        if not isinstance(arg, str) or not arg or any(ch.isspace() for ch in arg):
            raise MCFError("SSH remote arguments must be whitespace-free tokens")

    cmd = [
        "ssh",
        "-T",
        "-p", str(port),
        "-i", str(identity_file),
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "ClearAllForwardings=yes",
        "-o", "ConnectTimeout=15",
        f"{user}@{host}",
        *remote_args,
    ]
    try:
        if payload_path is None:
            completed = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        else:
            with payload_path.open("rb") as payload:
                completed = subprocess.run(
                    cmd,
                    stdin=payload,
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                    check=False,
                )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MCFError("SSH coordinator transport failed") from exc
    if completed.returncode != 0:
        raise MCFError(f"SSH gateway rejected request rc={completed.returncode}")
    try:
        doc = json.loads(completed.stdout)
    except (ValueError, TypeError) as exc:
        raise MCFError("SSH gateway returned invalid JSON") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("status"), str):
        raise MCFError("SSH gateway response missing status")
    return doc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("bundle")
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--batch", required=True)
    p.add_argument("--output-root", required=True, type=Path)

    p = sub.add_parser("server")
    p.add_argument("--node-id", required=True)
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--db", required=True, type=Path)
    p.add_argument("--results-root", required=True, type=Path)
    p.add_argument("--spool-root", required=True, type=Path)

    args = parser.parse_args(argv)
    try:
        plan = _load_plan(args.plan)
        if args.command == "bundle":
            result = build_batch_bundle(args.root, plan, args.batch, args.output_root)
        else:
            original = os.environ.get("SSH_ORIGINAL_COMMAND", "")
            result = execute_server_command(
                original,
                node_id=args.node_id,
                plan=plan,
                db=args.db,
                results_root=args.results_root,
                spool_root=args.spool_root,
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({"status": "SSH_DISTRIBUTED_GATEWAY_BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
