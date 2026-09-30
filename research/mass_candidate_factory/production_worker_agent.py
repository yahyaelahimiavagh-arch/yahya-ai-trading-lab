"""Single-entry control agent for portable YATL distributed workers.

Supports either:
- HTTPS coordinator transport (Cloudflare Worker/D1/R2), or
- SSH transport to the existing VPS with no additional paid service.

The agent does not itself authorize full performance. The execution-capable
micro-shard runner remains separately locked by a content-addressed Director
authorization artifact.
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
from .production_ssh_gateway import build_batch_bundle, ssh_request
from .production_worker_bundle import verify_bundle
from .production_worker_client import (
    claim,
    pause_request,
    paused,
    release,
    resume,
    status as coordinator_status,
)


def _load(path: Path) -> dict:
    doc = json.loads(path.read_bytes())
    if not isinstance(doc, dict):
        raise MCFError("expected JSON object")
    return doc


def _node_id(args) -> str:
    node_id = args.node_id or os.environ.get("YATL_NODE_ID", "")
    if not node_id:
        raise MCFError("YATL_NODE_ID is required")
    return node_id


def _https_config(args) -> tuple[str, str]:
    coordinator_url = args.coordinator_url or os.environ.get("YATL_COORDINATOR_URL", "")
    token = os.environ.get("YATL_NODE_TOKEN", "")
    if not coordinator_url or not token:
        raise MCFError("HTTPS transport requires YATL_COORDINATOR_URL and YATL_NODE_TOKEN")
    return coordinator_url, token


def _ssh_config() -> dict:
    required = {
        "host": os.environ.get("YATL_SSH_HOST", ""),
        "user": os.environ.get("YATL_SSH_USER", ""),
        "identity_file": os.environ.get("YATL_SSH_IDENTITY", ""),
        "known_hosts": os.environ.get("YATL_SSH_KNOWN_HOSTS", ""),
    }
    if any(not value for value in required.values()):
        raise MCFError(
            "SSH transport requires YATL_SSH_HOST, YATL_SSH_USER, "
            "YATL_SSH_IDENTITY and YATL_SSH_KNOWN_HOSTS"
        )
    try:
        port = int(os.environ.get("YATL_SSH_PORT", "22"))
    except ValueError as exc:
        raise MCFError("YATL_SSH_PORT must be an integer") from exc
    return {
        "host": required["host"],
        "user": required["user"],
        "identity_file": Path(required["identity_file"]),
        "known_hosts": Path(required["known_hosts"]),
        "port": port,
    }


def _ssh(remote_args: list[str], *, payload_path: Path | None = None) -> dict:
    cfg = _ssh_config()
    return ssh_request(
        host=cfg["host"],
        user=cfg["user"],
        identity_file=cfg["identity_file"],
        known_hosts=cfg["known_hosts"],
        port=cfg["port"],
        remote_args=remote_args,
        payload_path=payload_path,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-id")
    parser.add_argument("--transport", choices=("https", "ssh"),
                        default=os.environ.get("YATL_COORDINATOR_TRANSPORT", "https"))
    parser.add_argument("--coordinator-url")
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("YATL_WORKER_ROOT", "./yatl-worker-state")))
    parser.add_argument("--plan", type=Path, default=Path(os.environ.get("YATL_DISTRIBUTED_PLAN", "./plan.json")))
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor")
    p.add_argument("--work-root", type=Path)

    p = sub.add_parser("claim")
    p.add_argument("batch", nargs="?")
    p.add_argument("--lease-seconds", type=int, default=7200)

    sub.add_parser("status")

    p = sub.add_parser("local-status")
    p.add_argument("batch")

    p = sub.add_parser("pause")
    p.add_argument("batch")

    p = sub.add_parser("ack-paused")
    p.add_argument("batch")

    p = sub.add_parser("resume")
    p.add_argument("batch")
    p.add_argument("--lease-seconds", type=int, default=7200)

    p = sub.add_parser("release")
    p.add_argument("batch")

    p = sub.add_parser("upload")
    p.add_argument("batch")

    p = sub.add_parser("verify-bundle")
    p.add_argument("--bundle-root", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path)

    args = parser.parse_args(argv)
    try:
        node_id = _node_id(args)

        if args.command == "doctor":
            result = preflight(node_id, args.work_root or args.root)
            result = {**result, "configured_transport": args.transport}
        else:
            plan = _load(args.plan)
            validate_plan(plan)
            args.root.mkdir(parents=True, exist_ok=True)

            if args.command == "verify-bundle":
                manifest = _load(args.manifest)
                result = verify_bundle(args.bundle_root, manifest, plan)
            elif args.command == "local-status":
                result = local_status(args.root, plan, args.batch)
            elif args.transport == "ssh":
                if args.command == "claim":
                    remote = (
                        ["claim-next", str(args.lease_seconds)]
                        if args.batch is None
                        else ["claim", args.batch, str(args.lease_seconds)]
                    )
                    result = _ssh(remote)
                elif args.command == "status":
                    result = _ssh(["status"])
                elif args.command == "pause":
                    request_pause(args.root, plan, args.batch)
                    remote = _ssh(["pause-request", args.batch])
                    result = {
                        "status": "PAUSE_REQUESTED",
                        "batch_code": args.batch,
                        "node_id": node_id,
                        "remote_status": remote.get("status"),
                    }
                elif args.command == "ack-paused":
                    remote = _ssh(["paused", args.batch])
                    result = {
                        "status": "PAUSED_SAFE",
                        "batch_code": args.batch,
                        "node_id": node_id,
                        "remote_status": remote.get("status"),
                    }
                elif args.command == "resume":
                    remote = _ssh(["resume", args.batch, str(args.lease_seconds)])
                    clear_pause(args.root, plan, args.batch)
                    result = {
                        "status": "BATCH_RESUMED",
                        "batch_code": args.batch,
                        "node_id": node_id,
                        "lease_until_ms": remote.get("lease_until_ms"),
                    }
                elif args.command == "release":
                    remote = _ssh(["release", args.batch])
                    clear_pause(args.root, plan, args.batch)
                    result = {
                        "status": "BATCH_RELEASED",
                        "batch_code": args.batch,
                        "node_id": node_id,
                        "remote_status": remote.get("status"),
                    }
                elif args.command == "upload":
                    bundle = build_batch_bundle(
                        args.root,
                        plan,
                        args.batch,
                        args.root / "transfer-out",
                    )
                    bundle_path = Path(bundle["bundle_path"])
                    remote = _ssh(
                        [
                            "upload",
                            args.batch,
                            str(bundle["batch_result_manifest_sha256"]),
                            str(bundle["bundle_bytes"]),
                            str(bundle["bundle_sha256"]),
                        ],
                        payload_path=bundle_path,
                    )
                    if remote.get("status") != "SSH_BATCH_INGESTED_ACCEPTED":
                        raise MCFError("SSH gateway did not accept verified batch ingest")
                    try:
                        bundle_path.unlink()
                    except OSError:
                        pass
                    result = {
                        **remote,
                        "local_bundle_removed_after_verified_ingest": not bundle_path.exists(),
                    }
                else:
                    raise MCFError("unsupported SSH worker command")
            else:
                coordinator_url, token = _https_config(args)
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
                elif args.command == "pause":
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
                else:
                    raise MCFError("unsupported HTTPS worker command")

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
