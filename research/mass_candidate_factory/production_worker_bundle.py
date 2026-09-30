"""Portable worker-bundle manifest for frozen MCF-PROD-001 runtime data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Mapping

from .models import MCFError, canonical, digest, guard_root, safe_path, write_once
from .production_distributed import validate_plan
from .production_runner_input import FrozenRunnerInput

SCHEMA = "MCF_DISTRIBUTED_WORKER_BUNDLE/1.0.0"


def _raw_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_bundle_manifest(
    runtime_root: Path,
    *,
    runner_input_relative: str,
    expected_runner_input_sha256: str,
    distributed_plan: Mapping[str, object],
    git_sha: str,
) -> dict:
    """Bind every byte needed by a portable worker, with no sealed evidence."""
    validate_plan(distributed_plan)
    if not isinstance(git_sha, str) or len(git_sha) != 40 or any(c not in "0123456789abcdef" for c in git_sha):
        raise MCFError("worker bundle requires exact git commit SHA")
    reader = FrozenRunnerInput(
        runtime_root,
        runner_input_relative,
        expected_runner_input_sha256,
    )
    objects = []

    input_path = safe_path(runtime_root, runner_input_relative)
    objects.append({
        "relative": runner_input_relative,
        "kind": "RUNNER_INPUT",
        "bytes": input_path.stat().st_size,
        "raw_sha256": _raw_sha(input_path),
    })

    rows = reader._doc["runtime_index"]["datasets"]
    for row in rows:
        for kind, key in (("DATA", "data_ref"), ("GAP_MAP", "gap_ref")):
            relative = str(row[key])
            path = safe_path(runtime_root, relative)
            if not path.is_file():
                raise MCFError("worker bundle runtime object missing")
            objects.append({
                "relative": relative,
                "kind": kind,
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "bytes": path.stat().st_size,
                "raw_sha256": _raw_sha(path),
            })

    relatives = [x["relative"] for x in objects]
    if len(relatives) != len(set(relatives)):
        raise MCFError("worker bundle duplicate object path")
    base = {
        "schema": SCHEMA,
        "generation_id": "MCF-PROD-001",
        "state": "WORKER_BUNDLE_FROZEN_NO_PERFORMANCE",
        "distributed_plan_sha256": distributed_plan["plan_sha256"],
        "git_sha": git_sha,
        "runner_input_relative": runner_input_relative,
        "runner_input_sha256": expected_runner_input_sha256,
        "runtime_index_sha256": reader._doc["runtime_index"]["index_sha256"],
        "membership_freeze_sha256": reader._doc["membership"]["freeze_sha256"],
        "dataset_count": reader._doc["runtime_index"]["dataset_count"],
        "object_count": len(objects),
        "total_bytes": sum(x["bytes"] for x in objects),
        "objects": objects,
        "safety": {
            "fresh_oos_included": False,
            "recent_reserve_included": False,
            "p10_included": False,
            "credentials_included": False,
            "performance_execution_authorized": False,
        },
    }
    if base["dataset_count"] != 525 or base["object_count"] != 1 + 2 * 525:
        raise MCFError("worker bundle does not contain exact accepted runtime matrix")
    return {**base, "bundle_manifest_sha256": digest(base)}


def validate_bundle_manifest(manifest: Mapping[str, object], distributed_plan: Mapping[str, object]) -> None:
    validate_plan(distributed_plan)
    base = {k: v for k, v in manifest.items() if k != "bundle_manifest_sha256"}
    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("generation_id") != "MCF-PROD-001"
        or manifest.get("state") != "WORKER_BUNDLE_FROZEN_NO_PERFORMANCE"
        or manifest.get("distributed_plan_sha256") != distributed_plan["plan_sha256"]
        or manifest.get("dataset_count") != 525
        or manifest.get("object_count") != 1051
        or manifest.get("safety") != {
            "fresh_oos_included": False,
            "recent_reserve_included": False,
            "p10_included": False,
            "credentials_included": False,
            "performance_execution_authorized": False,
        }
        or digest(base) != manifest.get("bundle_manifest_sha256")
    ):
        raise MCFError("worker bundle manifest boundary mismatch")
    objects = manifest.get("objects")
    if not isinstance(objects, list) or len(objects) != 1051:
        raise MCFError("worker bundle object inventory mismatch")
    relatives = []
    for row in objects:
        if (
            not isinstance(row, Mapping)
            or not isinstance(row.get("relative"), str)
            or row.get("kind") not in {"RUNNER_INPUT", "DATA", "GAP_MAP"}
            or not isinstance(row.get("bytes"), int)
            or row["bytes"] < 1
            or not isinstance(row.get("raw_sha256"), str)
            or len(row["raw_sha256"]) != 64
        ):
            raise MCFError("invalid worker bundle object")
        relatives.append(row["relative"])
    if len(set(relatives)) != len(relatives):
        raise MCFError("worker bundle duplicate object inventory")


def verify_bundle(root: Path, manifest: Mapping[str, object],
                  distributed_plan: Mapping[str, object]) -> dict:
    """Verify copied worker bytes without reading any outside path."""
    validate_bundle_manifest(manifest, distributed_plan)
    root = guard_root(root)
    checked_bytes = 0
    for row in manifest["objects"]:
        path = safe_path(root, row["relative"])
        if not path.is_file() or path.stat().st_size != row["bytes"] or _raw_sha(path) != row["raw_sha256"]:
            raise MCFError(f"worker bundle object mismatch: {row['relative']}")
        checked_bytes += row["bytes"]
    if checked_bytes != manifest["total_bytes"]:
        raise MCFError("worker bundle total byte reconciliation mismatch")
    # Re-open the runner input after byte validation to re-check semantic/code binding.
    FrozenRunnerInput(
        root,
        manifest["runner_input_relative"],
        manifest["runner_input_sha256"],
    )
    return {
        "status": "WORKER_BUNDLE_VERIFIED_NO_PERFORMANCE",
        "bundle_manifest_sha256": manifest["bundle_manifest_sha256"],
        "object_count": manifest["object_count"],
        "dataset_count": manifest["dataset_count"],
        "total_bytes": manifest["total_bytes"],
        "performance_execution_authorized": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("freeze")
    p.add_argument("--runtime-root", required=True, type=Path)
    p.add_argument("--runner-input-relative", required=True)
    p.add_argument("--expected-runner-input-sha256", required=True)
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--git-sha", required=True)
    p.add_argument("--output", required=True, type=Path)

    p = sub.add_parser("verify")
    p.add_argument("--runtime-root", required=True, type=Path)
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path)

    args = parser.parse_args(argv)
    try:
        plan = json.loads(args.plan.read_bytes())
        validate_plan(plan)
        if args.command == "freeze":
            doc = build_bundle_manifest(
                args.runtime_root,
                runner_input_relative=args.runner_input_relative,
                expected_runner_input_sha256=args.expected_runner_input_sha256,
                distributed_plan=plan,
                git_sha=args.git_sha,
            )
            write_once(args.output, canonical(doc))
            result = {
                "status": doc["state"],
                "bundle_manifest_sha256": doc["bundle_manifest_sha256"],
                "object_count": doc["object_count"],
                "dataset_count": doc["dataset_count"],
                "total_bytes": doc["total_bytes"],
                "performance_execution_authorized": False,
            }
        else:
            manifest = json.loads(args.manifest.read_bytes())
            result = verify_bundle(args.runtime_root, manifest, plan)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "WORKER_BUNDLE_BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
