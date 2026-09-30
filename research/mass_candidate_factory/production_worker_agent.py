"""Single-entry control agent for portable YATL distributed workers.

This is the operator UX for node enrollment/control/status/pause/resume/upload.
It intentionally contains no production performance execution command yet.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .models import MCFError
from .production_distributed import (
    build_batch_manifest,
    clear_pause,
    request_pause,
    status as local_status,
    validate_plan,
)
from .production_node_tools import preflight
from .production_result_transfer import upload_batch
from .production_worker_bundle import verify_bundle
from .production_worker_client import (
    claim,
    pause_request,
    paused,
    release,
    resume,
    status as coordinator_status,
)


def _env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise MCFError(f"{name} is required")
    return value


def _load(path: Path) -> dict:
    doc = json.loads(path.read_bytes())
    if not isinstance(doc, dict):
        raise MCFError("expected JSON object")
    return doc


def _config(args) -> tuple[str, str, str]:
    node_id = args.node_id or os.environ.get("YATL_NODE_ID", "")
    coordinator_url = args.coordinator_url or os.environ.get("YATL_COORDINATOR_URL", "")
    token = os.environ.get("YATL_NODE_TOKEN", "")
    if not node_id or not coordinator_url or not token:
        raise MCFError("YATL_NODE_ID, YATL_COORDINATOR_URL and YATL_NODE_TOKEN are required")
    return node_id, coordinator_url, token


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-id")
    parser.add_argument("--coordinator-url")
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("YATL_WORKER_ROOT", "./yatl-worker-state")))
    parser.add_argument("--plan", type=Path, default=Path(os.environ.get("YATL_DISTRIBUTED_PLAN", "./plan.json")))
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor")
    p.add_argument("--work-root", type=Path)

    p = sub.add_parser("claim")
    p.add_argument("batch", nargs="?")
    p.add_argument("--lease-seconds", type=int, default=900)

    sub.add_parser("status")

    p = sub.add_parser("local-status")
    p.add_argument("batch")

    p = sub.add_parser("pause")
    p.add_argument("batch")

    p = sub.add_parser("ack-paused")
    p.add_argument("batch")

    p = sub.add_parser("resume")
    p.add_argument("batch")
    p.add_argument("--lease-seconds", type=int, default=900)

    p = sub.add_parser("release")
    p.add_argument("batch")

    p = sub.add_parser("upload")
    p.add_argument("batch")

    p = sub.add_parser("verify-bundle")
    p.add_argument("--bundle-root", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path)

    args = parser.parse_args(argv)
    try:
        node_id, coordinator_url, token = _config(args)
        if args.command == "doctor":
            result = preflight(node_id, args.work_root or args.root)
        else:
            plan = _load(args.plan)
            validate_plan(plan)
            args.root.mkdir(parents=True, exist_ok=True)

            if args.command == "claim":
                result = claim(
                    coordinator_url,
                    node_id,
                    batch_code=args.batch,
                    lease_seconds=args.lease_seconds,
                    token=token,
                )
            elif args.command == "status":
                result = coordinator_status(coordinator_url, node_id, token=token)
            elif args.command == "local-status":
                result = local_status(args.root, plan, args.batch)
            elif args.command == "pause":
                # Mark local intent first so the future executor will not start a
                # new candidate after its current candidate finishes.
                request_pause(args.root, plan, args.batch)
                remote = pause_request(coordinator_url, node_id, args.batch, token=token)
                result = {
                    "status": "PAUSE_REQUESTED",
                    "batch_code": args.batch,
                    "node_id": node_id,
                    "remote_status": remote.get("status"),
                }
            elif args.command == "ack-paused":
                remote = paused(coordinator_url, node_id, args.batch, token=token)
                result = {
                    "status": "PAUSED_SAFE",
                    "batch_code": args.batch,
                    "node_id": node_id,
                    "remote_status": remote.get("status"),
                }
            elif args.command == "resume":
                remote = resume(
                    coordinator_url,
                    node_id,
                    args.batch,
                    lease_seconds=args.lease_seconds,
                    token=token,
                )
                clear_pause(args.root, plan, args.batch)
                result = {
                    "status": "BATCH_RESUMED",
                    "batch_code": args.batch,
                    "node_id": node_id,
                    "lease_until_ms": remote.get("lease_until_ms"),
                }
            elif args.command == "release":
                remote = release(coordinator_url, node_id, args.batch, token=token)
                clear_pause(args.root, plan, args.batch)
                result = {
                    "status": "BATCH_RELEASED",
                    "batch_code": args.batch,
                    "node_id": node_id,
                    "remote_status": remote.get("status"),
                }
            elif args.command == "upload":
                manifest = build_batch_manifest(args.root, plan, args.batch)
                result = upload_batch(
                    args.root,
                    plan,
                    manifest,
                    coordinator_url=coordinator_url,
                    node_id=node_id,
                    token=token,
                )
            elif args.command == "verify-bundle":
                manifest = _load(args.manifest)
                result = verify_bundle(args.bundle_root, manifest, plan)
            else:
                raise MCFError("unsupported worker agent command")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({
            "status": "WORKER_AGENT_BLOCKED",
            "reason": str(exc),
            "performance_execution_authorized": False,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
