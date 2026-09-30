"""Guarded distributed performance runner for MCF-PROD-001.

This module is execution-capable but fail-closed. It cannot run candidate
performance without a separate, content-addressed Director authorization
artifact that binds the exact distributed plan, runner input and Git commit.

A batch is executed one <=25-candidate micro-shard per child process so RSS is
bounded by process lifetime. Candidate results are immutable checkpoints, so a
restart skips already verified candidates and resumes deterministically.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping

from .models import MCFError, canonical, digest
from .production_distributed import (
    batch,
    candidate_completed,
    pause_requested,
    validate_plan,
    write_candidate_result,
)
from .production_runner_input import FrozenRunnerInput
from .production_runtime import ProductionRuntime

AUTH_SCHEMA = "MCF_DISTRIBUTED_PERFORMANCE_AUTHORIZATION/1.0.0"
AUTH_SCOPE = "DEVELOPMENT_FULL_6852"
ROOT = Path(__file__).resolve().parents[2]


def _load_canonical(path: Path) -> dict:
    raw = path.read_bytes()
    doc = json.loads(raw)
    if not isinstance(doc, dict) or canonical(doc) != raw:
        raise MCFError("expected canonical JSON object")
    return doc


def current_git_sha(repo_root: Path = ROOT) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MCFError("cannot resolve worker Git HEAD") from exc
    sha = completed.stdout.strip()
    if completed.returncode != 0 or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise MCFError("worker Git HEAD is not an exact commit SHA")
    return sha


def validate_authorization(
    authorization: Mapping[str, object],
    *,
    plan_sha256: str,
    runner_input_sha256: str,
    git_sha: str,
) -> dict:
    base = {k: v for k, v in authorization.items() if k != "authorization_sha256"}
    if (
        authorization.get("schema") != AUTH_SCHEMA
        or authorization.get("scope") != AUTH_SCOPE
        or authorization.get("authorized") is not True
        or authorization.get("plan_sha256") != plan_sha256
        or authorization.get("runner_input_sha256") != runner_input_sha256
        or authorization.get("git_sha") != git_sha
        or authorization.get("fresh_oos_read") is not False
        or authorization.get("recent_reserve_read") is not False
        or authorization.get("p10_read") is not False
        or authorization.get("p10_write") is not False
        or authorization.get("live") is not False
        or authorization.get("futures") is not False
        or authorization.get("leverage") is not False
        or authorization.get("short") is not False
        or digest(base) != authorization.get("authorization_sha256")
    ):
        raise MCFError("distributed performance authorization boundary mismatch")
    return dict(authorization)


def _microshard(plan: Mapping[str, object], batch_code: str, shard_code: str) -> Mapping[str, object]:
    item = batch(plan, batch_code)
    found = next((x for x in item["microshards"] if x["microshard_code"] == shard_code), None)
    if found is None:
        raise MCFError("micro-shard not in frozen distributed batch")
    if not 1 <= int(found["candidate_count"]) <= 25:
        raise MCFError("micro-shard exceeds bounded process size")
    return found


def run_microshard(
    *,
    root: Path,
    plan: Mapping[str, object],
    reader: FrozenRunnerInput,
    node_id: str,
    batch_code: str,
    shard_code: str,
    git_sha: str,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Execute one bounded micro-shard in the current process."""
    validate_plan(plan)
    shard = _microshard(plan, batch_code, shard_code)
    runtime = ProductionRuntime.from_frozen_input(reader)
    executed = 0
    skipped = 0

    for position, candidate in enumerate(shard["candidates"], 1):
        candidate_id = str(candidate["candidate_id"])
        if pause_requested(root, plan, batch_code):
            return {
                "status": "MICROSHARD_PAUSED_SAFE",
                "batch_code": batch_code,
                "microshard_code": shard_code,
                "executed": executed,
                "skipped_completed": skipped,
                "next_candidate_id": candidate_id,
            }
        if candidate_completed(root, plan, batch_code, candidate_id):
            skipped += 1
            continue
        try:
            result = runtime.run(candidate_id, director_authorized=True)
            write_candidate_result(
                root,
                plan,
                batch_code,
                candidate_id,
                node_id=node_id,
                git_sha=git_sha,
                runner_input_sha256=reader.expected_sha256,
                result=result,
            )
            executed += 1
            if progress is not None:
                progress({
                    "batch_code": batch_code,
                    "microshard_code": shard_code,
                    "position": position,
                    "microshard_total": int(shard["candidate_count"]),
                    "candidate_id": candidate_id,
                })
        finally:
            runtime.release_transient_features()
            gc.collect()

    return {
        "status": "MICROSHARD_COMPLETE",
        "batch_code": batch_code,
        "microshard_code": shard_code,
        "executed": executed,
        "skipped_completed": skipped,
        "candidate_count": int(shard["candidate_count"]),
    }


def run_batch_supervisor(
    *,
    root: Path,
    plan_path: Path,
    input_relative: str,
    expected_input_sha256: str,
    authorization_path: Path,
    node_id: str,
    batch_code: str,
    expected_git_sha: str,
    python_executable: str = sys.executable,
    module: str = "research.mass_candidate_factory.production_worker_runner",
    runner: Callable[..., object] = subprocess.run,
) -> dict:
    """Restart the Python worker after every micro-shard."""
    plan = _load_canonical(plan_path)
    validate_plan(plan)
    current = current_git_sha()
    if current != expected_git_sha:
        raise MCFError("worker Git HEAD differs from authorized commit")
    auth = _load_canonical(authorization_path)
    validate_authorization(
        auth,
        plan_sha256=str(plan["plan_sha256"]),
        runner_input_sha256=expected_input_sha256,
        git_sha=expected_git_sha,
    )
    item = batch(plan, batch_code)
    completed_shards = 0
    for shard in item["microshards"]:
        if pause_requested(root, plan, batch_code):
            return {
                "status": "BATCH_PAUSED_SAFE",
                "batch_code": batch_code,
                "completed_microshards_this_run": completed_shards,
            }
        cmd = [
            python_executable,
            "-m",
            module,
            "run-shard",
            "--root",
            str(root),
            "--plan",
            str(plan_path),
            "--runtime-root",
            str(ROOT if False else ""),  # replaced below by CLI supervisor
        ]
        # run_batch_supervisor is normally invoked through main(), which builds
        # the exact child command with runtime-root. Tests may inject a runner.
        raise MCFError("run_batch_supervisor requires explicit runtime-root")


def _child_command(args, shard_code: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "research.mass_candidate_factory.production_worker_runner",
        "run-shard",
        "--root", str(args.root),
        "--plan", str(args.plan),
        "--runtime-root", str(args.runtime_root),
        "--input-relative", args.input_relative,
        "--expected-input-sha256", args.expected_input_sha256,
        "--authorization", str(args.authorization),
        "--node-id", args.node_id,
        "--batch", args.batch,
        "--microshard", shard_code,
        "--expected-git-sha", args.expected_git_sha,
    ]


def _progress(row: Mapping[str, object]) -> None:
    print(
        "MCF_WORKER_PROGRESS "
        + json.dumps(dict(row), sort_keys=True, separators=(",", ":")),
        file=sys.stderr,
        flush=True,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("preflight", "run-shard", "run-batch"):
        p = sub.add_parser(name)
        p.add_argument("--root", required=True, type=Path)
        p.add_argument("--plan", required=True, type=Path)
        p.add_argument("--runtime-root", required=True, type=Path)
        p.add_argument("--input-relative", required=True)
        p.add_argument("--expected-input-sha256", required=True)
        p.add_argument("--authorization", type=Path)
        p.add_argument("--node-id", required=True)
        p.add_argument("--batch", required=True)
        p.add_argument("--expected-git-sha", required=True)
        if name == "run-shard":
            p.add_argument("--microshard", required=True)

    args = parser.parse_args(argv)
    try:
        plan = _load_canonical(args.plan)
        validate_plan(plan)
        git_sha = current_git_sha()
        if git_sha != args.expected_git_sha:
            raise MCFError("worker Git HEAD differs from expected commit")
        reader = FrozenRunnerInput(
            args.runtime_root,
            args.input_relative,
            args.expected_input_sha256,
        )
        item = batch(plan, args.batch)

        if args.command == "preflight":
            result = {
                "status": "DISTRIBUTED_WORKER_PREFLIGHT_COMPLETE_NO_PERFORMANCE",
                "plan_sha256": plan["plan_sha256"],
                "runner_input_sha256": args.expected_input_sha256,
                "git_sha": git_sha,
                "batch_code": args.batch,
                "microshard_count": len(item["microshards"]),
                "candidate_count": item["candidate_count"],
                "performance_execution_authorized": False,
            }
        else:
            if args.authorization is None:
                raise MCFError("separate Director authorization artifact is required")
            auth = _load_canonical(args.authorization)
            validate_authorization(
                auth,
                plan_sha256=str(plan["plan_sha256"]),
                runner_input_sha256=args.expected_input_sha256,
                git_sha=git_sha,
            )
            args.root.mkdir(parents=True, exist_ok=True)
            if args.command == "run-shard":
                result = run_microshard(
                    root=args.root,
                    plan=plan,
                    reader=reader,
                    node_id=args.node_id,
                    batch_code=args.batch,
                    shard_code=args.microshard,
                    git_sha=git_sha,
                    progress=_progress,
                )
            else:
                completed_shards = 0
                child_results = []
                for shard in item["microshards"]:
                    if pause_requested(args.root, plan, args.batch):
                        result = {
                            "status": "BATCH_PAUSED_SAFE",
                            "batch_code": args.batch,
                            "completed_microshards_this_run": completed_shards,
                            "child_results": child_results,
                        }
                        break
                    completed = subprocess.run(
                        _child_command(args, str(shard["microshard_code"])),
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    if completed.stderr:
                        sys.stderr.write(completed.stderr)
                        sys.stderr.flush()
                    if completed.returncode != 0:
                        raise MCFError(
                            f"micro-shard child failed: {shard['microshard_code']} rc={completed.returncode}"
                        )
                    try:
                        child = json.loads(completed.stdout)
                    except (ValueError, TypeError) as exc:
                        raise MCFError("micro-shard child returned invalid JSON") from exc
                    if child.get("status") not in {"MICROSHARD_COMPLETE", "MICROSHARD_PAUSED_SAFE"}:
                        raise MCFError("micro-shard child returned unexpected status")
                    child_results.append(child)
                    if child["status"] == "MICROSHARD_PAUSED_SAFE":
                        result = {
                            "status": "BATCH_PAUSED_SAFE",
                            "batch_code": args.batch,
                            "completed_microshards_this_run": completed_shards,
                            "child_results": child_results,
                        }
                        break
                    completed_shards += 1
                else:
                    result = {
                        "status": "BATCH_EXECUTION_COMPLETE",
                        "batch_code": args.batch,
                        "microshard_count": len(item["microshards"]),
                        "completed_microshards_this_run": completed_shards,
                        "child_results": child_results,
                    }

        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({
            "status": "DISTRIBUTED_WORKER_RUNNER_BLOCKED",
            "reason": str(exc),
            "performance_execution_authorized": False,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
