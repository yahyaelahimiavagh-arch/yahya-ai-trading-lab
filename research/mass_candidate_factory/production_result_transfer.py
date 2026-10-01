"""Automatic worker result relay and VPS ingest for distributed MCF execution.

Workers upload compact result artifacts and a batch manifest to the Cloudflare
coordinator/R2 relay. The VPS can then pull, hash-verify, reconcile, and mark the
batch ingested without manual file transfer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Mapping

from .models import MCFError, canonical, safe_path, write_once
from .production_distributed import (
    validate_plan,
    validate_batch_manifest_structure,
    verify_batch_manifest,
)
from .production_worker_client import ready, request_json

DEFAULT_TIMEOUT_SECONDS = 60
MAX_DOWNLOAD_BYTES = 16 * 1024 * 1024


def _env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise MCFError(f"{name} is required")
    return value


def _raw_sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _https(base: str) -> str:
    if not isinstance(base, str) or not base.startswith("https://"):
        raise MCFError("coordinator URL must use https")
    return base.rstrip("/")


def _put_bytes(
    base_url: str,
    path: str,
    *,
    token: str,
    node_id: str,
    payload: bytes,
    semantic_sha256: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    if not payload:
        raise MCFError("cannot upload empty result artifact")
    raw_sha = _raw_sha_bytes(payload)
    req = urllib.request.Request(
        _https(base_url) + path,
        data=payload,
        method="PUT",
        headers={
            "authorization": f"Bearer {token}",
            "x-yatl-node": node_id,
            "x-yatl-body-sha256": raw_sha,
            "x-yatl-semantic-sha256": semantic_sha256,
            "content-type": "application/json",
            "accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            detail = json.loads(raw)
        except (ValueError, TypeError):
            detail = {"status": f"HTTP_{exc.code}"}
        raise MCFError(f"result relay rejected upload: {detail.get('status', exc.code)}") from exc
    except urllib.error.URLError as exc:
        raise MCFError(f"result relay unavailable: {exc.reason}") from exc
    try:
        doc = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise MCFError("result relay returned non-JSON upload response") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("status"), str):
        raise MCFError("result relay returned invalid upload response")
    if doc.get("raw_sha256") not in (None, raw_sha):
        raise MCFError("result relay raw SHA acknowledgement mismatch")
    return doc


def upload_batch(
    root: Path,
    plan: Mapping[str, object],
    manifest: Mapping[str, object],
    *,
    coordinator_url: str,
    node_id: str,
    token: str | None = None,
) -> dict:
    """Upload one already-complete local batch and mark it ready for VPS ingest."""
    validate_plan(plan)
    validate_batch_manifest_structure(plan, manifest)
    verify_batch_manifest(root, plan, manifest)
    token = token or _env("YATL_NODE_TOKEN")
    batch_code = str(manifest["batch_code"])

    uploaded = 0
    uploaded_bytes = 0
    for row in manifest["artifacts"]:
        candidate_id = str(row["candidate_id"])
        semantic_sha = str(row["result_artifact_sha256"])
        relative = f"results/{batch_code}/{candidate_id}/result-{semantic_sha}.json"
        path = safe_path(root, relative)
        payload = path.read_bytes()
        response = _put_bytes(
            coordinator_url,
            f"/v1/artifact/{batch_code}/{candidate_id}/{semantic_sha}",
            token=token,
            node_id=node_id,
            payload=payload,
            semantic_sha256=semantic_sha,
        )
        if response.get("status") != "RESULT_ARTIFACT_STORED":
            raise MCFError("result relay did not confirm candidate artifact")
        uploaded += 1
        uploaded_bytes += len(payload)

    manifest_payload = canonical(dict(manifest))
    manifest_sha = str(manifest["batch_result_manifest_sha256"])
    response = _put_bytes(
        coordinator_url,
        f"/v1/manifest/{batch_code}/{manifest_sha}",
        token=token,
        node_id=node_id,
        payload=manifest_payload,
        semantic_sha256=manifest_sha,
    )
    if response.get("status") != "BATCH_MANIFEST_STORED":
        raise MCFError("result relay did not confirm batch manifest")

    ready_response = ready(
        coordinator_url,
        node_id,
        batch_code,
        result_manifest_sha256=manifest_sha,
        result_count=int(manifest["candidate_count"]),
        transfer_mode="R2",
        token=token,
    )
    if ready_response.get("status") != "BATCH_AWAITING_INGEST":
        raise MCFError("coordinator did not accept batch readiness")
    return {
        "status": "BATCH_UPLOADED_AWAITING_INGEST",
        "batch_code": batch_code,
        "candidate_count": uploaded,
        "uploaded_bytes": uploaded_bytes + len(manifest_payload),
        "batch_result_manifest_sha256": manifest_sha,
    }


def _admin_json(
    base_url: str,
    path: str,
    *,
    token: str,
    method: str = "GET",
    body: Mapping[str, object] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    return request_json(
        base_url,
        path,
        token=token,
        method=method,
        body=body,
        timeout=timeout,
    )


def _get_object(
    base_url: str,
    key: str,
    *,
    token: str,
    expected_semantic_sha256: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> bytes:
    encoded = urllib.parse.quote(key, safe="")
    req = urllib.request.Request(
        _https(base_url) + f"/v1/admin/object/{encoded}",
        method="GET",
        headers={
            "authorization": f"Bearer {token}",
            "accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(MAX_DOWNLOAD_BYTES + 1)
            raw_header = response.headers.get("x-yatl-raw-sha256")
            semantic_header = response.headers.get("x-yatl-semantic-sha256")
    except urllib.error.HTTPError as exc:
        raise MCFError(f"R2 ingest download rejected: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise MCFError(f"R2 ingest unavailable: {exc.reason}") from exc
    if len(raw) > MAX_DOWNLOAD_BYTES:
        raise MCFError("R2 ingest object exceeds bounded download size")
    if semantic_header and semantic_header != expected_semantic_sha256:
        raise MCFError("R2 semantic SHA metadata mismatch")
    actual_raw = _raw_sha_bytes(raw)
    if raw_header and raw_header != actual_raw:
        raise MCFError("R2 raw SHA metadata mismatch")
    return raw


def ingest_batch_from_r2(
    root: Path,
    plan: Mapping[str, object],
    *,
    coordinator_url: str,
    batch_code: str,
    manifest_sha256: str,
    admin_token: str | None = None,
) -> dict:
    """VPS pull + immutable local save + full reconciliation + ingest acknowledgement."""
    validate_plan(plan)
    admin_token = admin_token or _env("YATL_ADMIN_TOKEN")
    plan_sha = str(plan["plan_sha256"])
    manifest_key = f"results/{plan_sha}/{batch_code}/batch-manifest-{manifest_sha256}.json"
    manifest_raw = _get_object(
        coordinator_url,
        manifest_key,
        token=admin_token,
        expected_semantic_sha256=manifest_sha256,
    )
    try:
        manifest = json.loads(manifest_raw)
    except (ValueError, TypeError) as exc:
        raise MCFError("downloaded batch manifest is not JSON") from exc
    if canonical(manifest) != manifest_raw:
        raise MCFError("downloaded batch manifest is not canonical")
    validate_batch_manifest_structure(plan, manifest)
    if manifest.get("batch_result_manifest_sha256") != manifest_sha256:
        raise MCFError("downloaded batch manifest semantic identity mismatch")

    for row in manifest["artifacts"]:
        candidate_id = str(row["candidate_id"])
        semantic_sha = str(row["result_artifact_sha256"])
        key = f"results/{plan_sha}/{batch_code}/{candidate_id}/result-{semantic_sha}.json"
        raw = _get_object(
            coordinator_url,
            key,
            token=admin_token,
            expected_semantic_sha256=semantic_sha,
        )
        relative = f"results/{batch_code}/{candidate_id}/result-{semantic_sha}.json"
        write_once(safe_path(root, relative), raw)

    verified = verify_batch_manifest(root, plan, manifest)
    acknowledgement = _admin_json(
        coordinator_url,
        "/v1/ingested",
        token=admin_token,
        method="POST",
        body={
            "batch_code": batch_code,
            "result_manifest_sha256": manifest_sha256,
        },
    )
    if acknowledgement.get("status") != "BATCH_INGESTED":
        raise MCFError("coordinator did not acknowledge verified ingest")
    return {
        "status": "BATCH_INGESTED_ACCEPTED",
        "batch_code": batch_code,
        "candidate_count": verified["candidate_count"],
        "batch_result_manifest_sha256": manifest_sha256,
    }


def ingest_ready_batches_once(
    root: Path,
    plan: Mapping[str, object],
    *,
    coordinator_url: str,
    admin_token: str | None = None,
) -> dict:
    """One bounded polling iteration for a VPS timer/service."""
    validate_plan(plan)
    admin_token = admin_token or _env("YATL_ADMIN_TOKEN")
    status_doc = _admin_json(
        coordinator_url,
        "/v1/status",
        token=admin_token,
        method="GET",
    )
    accepted = []
    skipped = []
    for row in status_doc.get("batches", ()):
        if row.get("state") != "AWAITING_INGEST":
            continue
        if row.get("transfer_mode") != "R2":
            skipped.append({
                "batch_code": row.get("batch_code"),
                "reason": "NON_R2_TRANSFER_MODE",
            })
            continue
        accepted.append(ingest_batch_from_r2(
            root,
            plan,
            coordinator_url=coordinator_url,
            batch_code=str(row["batch_code"]),
            manifest_sha256=str(row["result_manifest_sha256"]),
            admin_token=admin_token,
        ))
    return {
        "status": "AUTO_INGEST_ITERATION_COMPLETE",
        "ingested_count": len(accepted),
        "ingested": accepted,
        "skipped": skipped,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coordinator-url", default=os.environ.get("YATL_COORDINATOR_URL"))
    parser.add_argument("--plan", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("upload-batch")
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--node-id", required=True)

    p = sub.add_parser("ingest-batch")
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--batch", required=True)
    p.add_argument("--manifest-sha256", required=True)

    p = sub.add_parser("ingest-once")
    p.add_argument("--root", required=True, type=Path)

    args = parser.parse_args(argv)
    try:
        if not args.coordinator_url:
            raise MCFError("coordinator URL is required via arg or YATL_COORDINATOR_URL")
        plan = json.loads(args.plan.read_bytes())
        validate_plan(plan)
        if args.command == "upload-batch":
            manifest = json.loads(args.manifest.read_bytes())
            result = upload_batch(
                args.root,
                plan,
                manifest,
                coordinator_url=args.coordinator_url,
                node_id=args.node_id,
            )
        elif args.command == "ingest-batch":
            result = ingest_batch_from_r2(
                args.root,
                plan,
                coordinator_url=args.coordinator_url,
                batch_code=args.batch,
                manifest_sha256=args.manifest_sha256,
            )
        else:
            result = ingest_ready_batches_once(
                args.root,
                plan,
                coordinator_url=args.coordinator_url,
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "RESULT_TRANSFER_BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
