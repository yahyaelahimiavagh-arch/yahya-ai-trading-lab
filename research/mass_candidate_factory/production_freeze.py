"""Materialize and verify the frozen MCF-PROD-001 executable identity set.

This module is intentionally pre-outcome only. It reads frozen governance
documents and candidate identity logic, never market data or performance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .models import MCFError, canonical, safe_path, write_once
from .production_generator import freeze_executable_generation
from .production_rules import BLOCKED_FAMILIES

ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_PATH = (
    ROOT
    / "docs/research/alpha-factory/"
    "MCF-PROD-001-PREOUTCOME-FREEZE-CHECKPOINT-v1.0.json"
)
ARTIFACT_DIR = "mcf-prod-001-preoutcome-freeze"
VERSION = "MCF_PRODUCTION_VPS_FREEZE/1.0.0"


def _checkpoint() -> dict:
    row = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    if row.get("schema") != "MCF_PROD_001_PREOUTCOME_FREEZE_CHECKPOINT/1.0.0":
        raise MCFError("wrong MCF-PROD-001 freeze checkpoint schema")
    if row.get("generation_id") != "MCF-PROD-001":
        raise MCFError("wrong MCF-PROD-001 freeze checkpoint generation")
    if row.get("state") != "PRE_OUTCOME_IDENTITY_FREEZE_REPRODUCED":
        raise MCFError("MCF-PROD-001 checkpoint is not accepted pre-outcome freeze")
    return row


def _jsonl(rows) -> bytes:
    return b"".join(canonical(row) for row in rows)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_payloads() -> tuple[dict, dict[str, bytes]]:
    checkpoint = _checkpoint()
    frozen = freeze_executable_generation(BLOCKED_FAMILIES)
    summary = frozen["summary"]

    generation = checkpoint["generation"]
    expected = checkpoint["executable_freeze"]

    exact_pairs = {
        "pre_block_structurally_valid_count": generation["structurally_valid_count"],
        "blocked_implementation_count": checkpoint["implementation_blockers"]["blocked_candidate_count"],
        "executable_candidate_count": expected["executable_candidate_count"],
        "candidate_ledger_sha256": expected["candidate_ledger_sha256"],
        "neighbor_graph_sha256": expected["neighbor_graph_sha256"],
        "freeze_sha256": expected["freeze_sha256"],
        "maximum_single_family_fraction": expected["maximum_single_family_fraction"],
        "combined_trend_breakout_fraction": expected["combined_trend_breakout_fraction"],
    }
    for key, wanted in exact_pairs.items():
        if summary.get(key) != wanted:
            raise MCFError(f"checkpoint mismatch: {key}")

    expected_family_counts = tuple(sorted(checkpoint["executable_family_counts"].items()))
    if tuple(summary["executable_family_counts"]) != expected_family_counts:
        raise MCFError("checkpoint mismatch: executable family counts")

    registered = [
        {"candidate_id": candidate_id, "candidate_spec_sha256": candidate_spec_sha256}
        for candidate_id, candidate_spec_sha256 in frozen["registered_candidates"]
    ]
    if len(registered) != expected["executable_candidate_count"]:
        raise MCFError("registered candidate count mismatch")

    first = expected["first_executable_candidate"]
    last = expected["last_executable_candidate"]
    if registered[0] != first or registered[-1] != last:
        raise MCFError("registered candidate endpoint mismatch")

    payloads = {
        "freeze-summary.json": canonical(summary),
        "registered-candidates.jsonl": _jsonl(registered),
        "blocked-candidates.jsonl": _jsonl(frozen["blocked"]),
        "neighbor-graph.json": canonical(frozen["neighbor_graph"]),
    }

    manifest = {
        "schema": VERSION,
        "generation_id": "MCF-PROD-001",
        "state": "PRE_OUTCOME_VPS_FREEZE_MATERIALIZED",
        "checkpoint_file": str(CHECKPOINT_PATH.relative_to(ROOT)),
        "freeze_sha256": summary["freeze_sha256"],
        "candidate_ledger_sha256": summary["candidate_ledger_sha256"],
        "neighbor_graph_sha256": summary["neighbor_graph_sha256"],
        "executable_candidate_count": summary["executable_candidate_count"],
        "blocked_implementation_count": summary["blocked_implementation_count"],
        "artifacts": {
            name: {"sha256": _sha(payload), "bytes": len(payload)}
            for name, payload in sorted(payloads.items())
        },
        "safety": {
            "performance_read": False,
            "fresh_oos_read": False,
            "recent_reserve_read": False,
            "p10_read": False,
            "p10_write": False,
            "live": False,
            "p11_locked": True,
        },
    }
    payloads["manifest.json"] = canonical(manifest)
    return manifest, payloads


def _target(root: Path, name: str) -> Path:
    return safe_path(root, f"{ARTIFACT_DIR}/{name}")


def materialize(root: Path) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise MCFError("VPS freeze root must already exist and be a directory")

    manifest, payloads = build_payloads()
    # Write manifest last: its presence means every referenced payload already
    # exists byte-for-byte. write_once makes reruns idempotent and collisions fail.
    for name in sorted(payloads):
        if name == "manifest.json":
            continue
        write_once(_target(root, name), payloads[name])
    write_once(_target(root, "manifest.json"), payloads["manifest.json"])
    return verify(root)


def verify(root: Path) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise MCFError("VPS freeze root must already exist and be a directory")

    expected_manifest, expected_payloads = build_payloads()
    for name, expected in expected_payloads.items():
        path = _target(root, name)
        if not path.is_file() or path.is_symlink():
            raise MCFError(f"missing VPS freeze artifact: {name}")
        actual = path.read_bytes()
        if actual != expected:
            raise MCFError(f"VPS freeze artifact mismatch: {name}")

    manifest = json.loads(_target(root, "manifest.json").read_text(encoding="utf-8"))
    if manifest != expected_manifest:
        raise MCFError("VPS freeze manifest mismatch")
    return {
        "schema": VERSION,
        "status": "VERIFIED",
        "artifact_dir": ARTIFACT_DIR,
        "freeze_sha256": manifest["freeze_sha256"],
        "candidate_ledger_sha256": manifest["candidate_ledger_sha256"],
        "neighbor_graph_sha256": manifest["neighbor_graph_sha256"],
        "executable_candidate_count": manifest["executable_candidate_count"],
        "blocked_implementation_count": manifest["blocked_implementation_count"],
        "performance_read": False,
        "fresh_oos_read": False,
        "recent_reserve_read": False,
        "p10_read": False,
        "p10_write": False,
        "live": False,
        "p11_locked": True,
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("materialize", "verify"))
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args(argv)

    result = materialize(args.root) if args.command == "materialize" else verify(args.root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
