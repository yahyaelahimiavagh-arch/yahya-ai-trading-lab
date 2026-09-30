"""Autonomous SSH worker loop for distributed MCF-PROD-001.

The loop is fail-closed:
- validates the exact Git/plan/runner-input identities;
- requires the separate content-addressed Director authorization artifact;
- claims one batch at a time from the VPS over restricted SSH;
- runs each <=25 candidate micro-shard in a fresh child process;
- renews the coordinator lease while the child is running;
- uploads a complete verified batch to the VPS;
- repeats until all 14 batches are ingested.

No Cloudflare service is required by this orchestrator.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Mapping

from .models import MCFError, canonical
from .production_distributed import batch, validate_plan
from .production_ssh_gateway import build_batch_bundle, ssh_request
from .production_worker_runner import current_git_sha, validate_authorization

ROOT = Path(__file__).resolve().parents[2]


def _load_canonical(path: Path) -> dict:
    raw = path.read_bytes()
    doc = json.loads(raw)
    if not isinstance(doc, dict) or canonical(doc) != raw:
        raise MCFError("expected canonical JSON object")
    return doc


class SshControl:
    def __init__(
        self,
        *,
        node_id: str,
        host: str,
        user: str,
        identity_file: Path,
        known_hosts: Path,
        port: int,
    ):
        self.node_id = node_id
        self.host = host
        self.user = user
        self.identity_file = identity_file
        self.known_hosts = known_hosts
        self.port = port

    @classmethod
    def from_environment(cls, node_id: str):
        host = os.environ.get("YATL_SSH_HOST", "")
        user = os.environ.get("YATL_SSH_USER", "")
        identity = os.environ.get("YATL_SSH_IDENTITY", "")
        known = os.environ.get("YATL_SSH_KNOWN_HOSTS", "")
        try:
            port = int(os.environ.get("YATL_SSH_PORT", "22"))
        except ValueError as exc:
            raise MCFError("YATL_SSH_PORT must be an integer") from exc
        if not all((host, user, identity, known)):
            raise MCFError(
                "SSH auto-worker requires YATL_SSH_HOST, YATL_SSH_USER, "
                "YATL_SSH_IDENTITY and YATL_SSH_KNOWN_HOSTS"
            )
        return cls(
            node_id=node_id,
            host=host,
            user=user,
            identity_file=Path(identity),
            known_hosts=Path(known),
            port=port,
        )

    def call(self, args: list[str], *, payload_path: Path | None = None) -> dict:
        return ssh_request(
            host=self.host,
            user=self.user,
            identity_file=self.identity_file,
            known_hosts=self.known_hosts,
            port=self.port,
            remote_args=args,
            payload_path=payload_path,
            timeout=3600 if payload_path is not None else 120,
        )

    def status(self) -> dict:
        return self.call(["status"])

    def claim_next(self, lease_seconds: int) -> dict:
        return self.call(["claim-next", str(lease_seconds)])

    def heartbeat(self, batch_code: str, lease_seconds: int) -> dict:
        return self.call(["heartbeat", batch_code, str(lease_seconds)])

    def upload_bundle(self, batch_code: str, bundle: Mapping[str, object]) -> dict:
        path = Path(str(bundle["bundle_path"]))
        return self.call(
            [
                "upload",
                batch_code,
                str(bundle["batch_result_manifest_sha256"]),
                str(bundle["bundle_bytes"]),
                str(bundle["bundle_sha256"]),
            ],
            payload_path=path,
        )


def _child_command(
    *,
    root: Path,
    plan_path: Path,
    runtime_root: Path,
    input_relative: str,
    runner_input_sha256: str,
    authorization_path: Path,
    node_id: str,
    batch_code: str,
    microshard_code: str,
    git_sha: str,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "research.mass_candidate_factory.production_worker_runner",
        "run-shard",
        "--root", str(root),
        "--plan", str(plan_path),
        "--runtime-root", str(runtime_root),
        "--input-relative", input_relative,
        "--expected-input-sha256", runner_input_sha256,
        "--authorization", str(authorization_path),
        "--node-id", node_id,
        "--batch", batch_code,
        "--microshard", microshard_code,
        "--expected-git-sha", git_sha,
    ]


def run_child_with_heartbeat(
    command: list[str],
    *,
    batch_code: str,
    control: SshControl,
    lease_seconds: int,
    heartbeat_seconds: int,
    popen_factory=subprocess.Popen,
    monotonic=time.monotonic,
    sleeper=time.sleep,
) -> dict:
    if heartbeat_seconds < 15 or heartbeat_seconds >= lease_seconds:
        raise MCFError("heartbeat interval must be >=15s and shorter than lease")
    control.heartbeat(batch_code, lease_seconds)
    process = popen_factory(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
    )
    next_heartbeat = monotonic() + heartbeat_seconds
    while process.poll() is None:
        sleeper(min(5, heartbeat_seconds))
        now = monotonic()
        if now >= next_heartbeat:
            control.heartbeat(batch_code, lease_seconds)
            next_heartbeat = now + heartbeat_seconds

    stdout, _ = process.communicate()
    if process.returncode != 0:
        raise MCFError(f"micro-shard child failed rc={process.returncode}")
    try:
        result = json.loads(stdout)
    except (ValueError, TypeError) as exc:
        raise MCFError("micro-shard child returned invalid JSON") from exc
    if not isinstance(result, dict) or result.get("status") not in {
        "MICROSHARD_COMPLETE",
        "MICROSHARD_PAUSED_SAFE",
    }:
        raise MCFError("micro-shard child returned unexpected status")
    return result


def run_auto_worker(
    *,
    runtime_root: Path,
    worker_root: Path,
    authorization_path: Path,
    node_id: str,
    lease_seconds: int = 1800,
    heartbeat_seconds: int = 300,
    max_batches: int = 0,
    retry_seconds: int = 60,
    max_control_failures: int = 12,
) -> dict:
    if not 300 <= lease_seconds <= 86400:
        raise MCFError("auto-worker lease outside safe range")
    if max_batches < 0 or retry_seconds < 1 or max_control_failures < 1:
        raise MCFError("invalid auto-worker bounds")

    plan_path = runtime_root / "distributed-plan.json"
    manifest_path = runtime_root / "worker-bundle-manifest.json"
    plan = _load_canonical(plan_path)
    validate_plan(plan)
    manifest = _load_canonical(manifest_path)

    runner_sha = str(manifest.get("runner_input_sha256", ""))
    input_relative = str(manifest.get("runner_input_relative", ""))
    git_sha = current_git_sha()
    if manifest.get("git_sha") != git_sha:
        raise MCFError("worker bundle Git identity differs from current HEAD")

    authorization = _load_canonical(authorization_path)
    validate_authorization(
        authorization,
        plan_sha256=str(plan["plan_sha256"]),
        runner_input_sha256=runner_sha,
        git_sha=git_sha,
    )

    control = SshControl.from_environment(node_id)
    worker_root.mkdir(parents=True, exist_ok=True)
    completed_batches: list[str] = []
    control_failures = 0

    while max_batches == 0 or len(completed_batches) < max_batches:
        report = control.status()
        counts = report.get("counts", {})
        if int(counts.get("INGESTED", 0)) == int(plan["batch_count"]):
            return {
                "status": "AUTO_WORKER_GLOBAL_COMPLETE",
                "node_id": node_id,
                "completed_batches_this_run": completed_batches,
                "global_ingested_batches": int(plan["batch_count"]),
            }

        try:
            claimed = control.claim_next(lease_seconds)
            control_failures = 0
        except MCFError:
            control_failures += 1
            if control_failures >= max_control_failures:
                raise
            time.sleep(retry_seconds)
            continue

        if claimed.get("status") != "BATCH_CLAIMED":
            raise MCFError("coordinator returned unexpected claim status")
        batch_code = str(claimed["batch_code"])
        frozen_batch = batch(plan, batch_code)

        for shard in frozen_batch["microshards"]:
            child = run_child_with_heartbeat(
                _child_command(
                    root=worker_root,
                    plan_path=plan_path,
                    runtime_root=runtime_root,
                    input_relative=input_relative,
                    runner_input_sha256=runner_sha,
                    authorization_path=authorization_path,
                    node_id=node_id,
                    batch_code=batch_code,
                    microshard_code=str(shard["microshard_code"]),
                    git_sha=git_sha,
                ),
                batch_code=batch_code,
                control=control,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
            )
            if child["status"] == "MICROSHARD_PAUSED_SAFE":
                return {
                    "status": "AUTO_WORKER_PAUSED_SAFE",
                    "node_id": node_id,
                    "batch_code": batch_code,
                    "microshard_code": shard["microshard_code"],
                    "completed_batches_this_run": completed_batches,
                }

        control.heartbeat(batch_code, lease_seconds)
        bundle = build_batch_bundle(
            worker_root,
            plan,
            batch_code,
            worker_root / "transfer-out",
        )
        accepted = control.upload_bundle(batch_code, bundle)
        if accepted.get("status") != "SSH_BATCH_INGESTED_ACCEPTED":
            raise MCFError("VPS did not acknowledge verified batch ingest")
        try:
            Path(str(bundle["bundle_path"])).unlink()
        except OSError:
            pass
        completed_batches.append(batch_code)

    return {
        "status": "AUTO_WORKER_BATCH_LIMIT_REACHED",
        "node_id": node_id,
        "completed_batches_this_run": completed_batches,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--worker-root", required=True, type=Path)
    parser.add_argument("--authorization", required=True, type=Path)
    parser.add_argument("--node-id", default=os.environ.get("YATL_NODE_ID"))
    parser.add_argument("--lease-seconds", type=int, default=1800)
    parser.add_argument("--heartbeat-seconds", type=int, default=300)
    parser.add_argument("--max-batches", type=int, default=0)
    parser.add_argument("--retry-seconds", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        if not args.node_id:
            raise MCFError("YATL_NODE_ID is required")
        result = run_auto_worker(
            runtime_root=args.runtime_root,
            worker_root=args.worker_root,
            authorization_path=args.authorization,
            node_id=args.node_id,
            lease_seconds=args.lease_seconds,
            heartbeat_seconds=args.heartbeat_seconds,
            max_batches=args.max_batches,
            retry_seconds=args.retry_seconds,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({
            "status": "AUTO_WORKER_BLOCKED",
            "reason": str(exc),
            "performance_execution_authorized": False,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
