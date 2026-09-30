"""Portable worker-bundle manifest for frozen MCF-PROD-001 runtime data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
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



ARCHIVE_MANIFEST_MEMBER = "worker-bundle-manifest.json"
ARCHIVE_PLAN_MEMBER = "distributed-plan.json"
ARCHIVE_PAYLOAD_PREFIX = "payload/"


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100600 << 16
    return info


def _archive_sha(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
            total += len(chunk)
    return h.hexdigest(), total


def archive_bundle(
    runtime_root: Path,
    manifest: Mapping[str, object],
    distributed_plan: Mapping[str, object],
    output_root: Path,
) -> dict:
    """Create one portable compressed archive after full byte verification."""
    validate_bundle_manifest(manifest, distributed_plan)
    verify_bundle(runtime_root, manifest, distributed_plan)
    output_root.mkdir(parents=True, exist_ok=True)
    guard_root(output_root)

    fd, tmp_name = tempfile.mkstemp(prefix=".partial-worker-bundle-", dir=output_root)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with zipfile.ZipFile(
            tmp,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as archive:
            archive.writestr(_zip_info(ARCHIVE_MANIFEST_MEMBER), canonical(dict(manifest)))
            archive.writestr(_zip_info(ARCHIVE_PLAN_MEMBER), canonical(dict(distributed_plan)))
            for row in manifest["objects"]:
                source = safe_path(runtime_root, str(row["relative"]))
                member = ARCHIVE_PAYLOAD_PREFIX + str(row["relative"])
                info = _zip_info(member)
                with source.open("rb") as src, archive.open(info, "w", force_zip64=True) as dst:
                    for chunk in iter(lambda: src.read(1024 * 1024), b""):
                        dst.write(chunk)

        raw_sha, archive_bytes = _archive_sha(tmp)
        name = (
            f"worker-runtime-{manifest['bundle_manifest_sha256']}-"
            f"{raw_sha}.zip"
        )
        target = safe_path(output_root, name)
        try:
            os.link(tmp, target)
        except FileExistsError:
            old_sha, old_bytes = _archive_sha(target)
            if old_sha != raw_sha or old_bytes != archive_bytes:
                raise MCFError("worker bundle archive collision")
        return {
            "status": "WORKER_BUNDLE_ARCHIVE_READY_NO_PERFORMANCE",
            "bundle_manifest_sha256": manifest["bundle_manifest_sha256"],
            "archive_sha256": raw_sha,
            "archive_bytes": archive_bytes,
            "archive_path": str(target),
            "object_count": manifest["object_count"],
            "dataset_count": manifest["dataset_count"],
            "performance_execution_authorized": False,
        }
    finally:
        if tmp.exists():
            tmp.unlink()


def _extract_verified_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    target: Path,
    expected_bytes: int,
    expected_sha256: str,
) -> None:
    if info.is_dir() or info.file_size != expected_bytes:
        raise MCFError("worker archive member size/type mismatch")
    mode = (info.external_attr >> 16) & 0o170000
    if mode not in (0, 0o100000):
        raise MCFError("worker archive contains non-regular payload member")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_symlink() or target.stat().st_size != expected_bytes or _raw_sha(target) != expected_sha256:
            raise MCFError("existing worker runtime object collision")
        return

    fd, tmp_name = tempfile.mkstemp(prefix=".partial-runtime-", dir=target.parent)
    tmp = Path(tmp_name)
    h = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(fd, "wb") as dst, archive.open(info, "r") as src:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > expected_bytes:
                    raise MCFError("worker archive member exceeds declared size")
                h.update(chunk)
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())
        if total != expected_bytes or h.hexdigest() != expected_sha256:
            raise MCFError("worker archive member hash mismatch")
        try:
            os.link(tmp, target)
        except FileExistsError:
            if target.is_symlink() or target.stat().st_size != expected_bytes or _raw_sha(target) != expected_sha256:
                raise MCFError("concurrent worker runtime object collision")
    finally:
        if tmp.exists():
            tmp.unlink()


def import_bundle_archive(
    archive_path: Path,
    runtime_root: Path,
    distributed_plan: Mapping[str, object] | None = None,
) -> dict:
    """Safely import a worker archive, its plan, and reconstructed runtime."""
    runtime_root.mkdir(parents=True, exist_ok=True)
    guard_root(runtime_root)
    with zipfile.ZipFile(archive_path, mode="r") as archive:
        infos = archive.infolist()
        names = [x.filename for x in infos]
        if (
            len(names) != len(set(names))
            or ARCHIVE_MANIFEST_MEMBER not in names
            or ARCHIVE_PLAN_MEMBER not in names
        ):
            raise MCFError("worker archive member inventory invalid")
        plan_info = archive.getinfo(ARCHIVE_PLAN_MEMBER)
        if plan_info.file_size > 64 * 1024 * 1024:
            raise MCFError("worker archive distributed plan exceeds bound")
        plan_raw = archive.read(plan_info)
        embedded_plan = json.loads(plan_raw)
        if not isinstance(embedded_plan, Mapping) or canonical(embedded_plan) != plan_raw:
            raise MCFError("worker archive distributed plan is not canonical")
        validate_plan(embedded_plan)
        if distributed_plan is not None and dict(distributed_plan) != dict(embedded_plan):
            raise MCFError("worker archive distributed plan differs from expected plan")
        plan = dict(embedded_plan)

        manifest_info = archive.getinfo(ARCHIVE_MANIFEST_MEMBER)
        if manifest_info.file_size > 32 * 1024 * 1024:
            raise MCFError("worker archive manifest exceeds bound")
        manifest_raw = archive.read(manifest_info)
        manifest = json.loads(manifest_raw)
        if not isinstance(manifest, Mapping) or canonical(manifest) != manifest_raw:
            raise MCFError("worker archive manifest is not canonical")
        validate_bundle_manifest(manifest, plan)

        expected_names = {ARCHIVE_MANIFEST_MEMBER, ARCHIVE_PLAN_MEMBER}
        for row in manifest["objects"]:
            expected_names.add(ARCHIVE_PAYLOAD_PREFIX + str(row["relative"]))
        if set(names) != expected_names:
            raise MCFError("worker archive contains missing or unexpected members")

        for row in manifest["objects"]:
            member = ARCHIVE_PAYLOAD_PREFIX + str(row["relative"])
            info = archive.getinfo(member)
            target = safe_path(runtime_root, str(row["relative"]))
            _extract_verified_member(
                archive,
                info,
                target=target,
                expected_bytes=int(row["bytes"]),
                expected_sha256=str(row["raw_sha256"]),
            )

    plan_path = safe_path(runtime_root, "distributed-plan.json")
    write_once(plan_path, canonical(plan))
    manifest_path = safe_path(runtime_root, "worker-bundle-manifest.json")
    write_once(manifest_path, canonical(dict(manifest)))
    verified = verify_bundle(runtime_root, manifest, plan)
    return {
        **verified,
        "status": "WORKER_BUNDLE_ARCHIVE_IMPORTED_VERIFIED_NO_PERFORMANCE",
        "archive_path": str(archive_path),
        "plan_path": str(plan_path),
        "manifest_path": str(manifest_path),
        "plan_sha256": plan["plan_sha256"],
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

    p = sub.add_parser("archive")
    p.add_argument("--runtime-root", required=True, type=Path)
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--output-root", required=True, type=Path)

    p = sub.add_parser("import-archive")
    p.add_argument("--runtime-root", required=True, type=Path)
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--archive", required=True, type=Path)

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
        elif args.command == "verify":
            manifest = json.loads(args.manifest.read_bytes())
            result = verify_bundle(args.runtime_root, manifest, plan)
        elif args.command == "archive":
            manifest = json.loads(args.manifest.read_bytes())
            result = archive_bundle(args.runtime_root, manifest, plan, args.output_root)
        else:
            result = import_bundle_archive(args.archive, args.runtime_root, plan)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "WORKER_BUNDLE_BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
