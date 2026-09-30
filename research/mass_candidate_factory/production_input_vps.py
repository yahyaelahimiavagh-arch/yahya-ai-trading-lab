"""Bounded VPS orchestration: data -> freeze -> verify, never performance.

Discovers only the already-accepted preflight/membership filenames and AF-01C
bootstrap metadata. Sealed directories are pruned before traversal or reads.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .models import MCFError, canonical, guard_root, safe_path
from .production_runtime_data import (
    EXPECTED_PLAN_SHA256, MEMBERSHIP_SHA, PREFLIGHT_SHA, materialize, read_json,
)
from .production_runner_input import FrozenRunnerInput, freeze_input, reconcile_datasets

FORBIDDEN = ("p10", "fresh_oos", "fresh-oos", "recent_reserve", "recent-reserve",
             "blind_oos", "blind-oos", "performance", "results")


def discover_evidence(search_root: Path) -> Path:
    search_root = guard_root(search_root)
    filename = f"membership-freeze-{MEMBERSHIP_SHA}.json"
    candidates = []
    for current, dirs, files in os.walk(search_root, followlinks=False):
        depth = len(Path(current).relative_to(search_root).parts)
        dirs[:] = [d for d in dirs if depth < 4 and not any(x in d.lower() for x in FORBIDDEN)
                   and not (Path(current) / d).is_symlink()
                   and d not in {"opportunity-data", "opportunity-data-pc"}]
        if filename in files and Path(current).name == "monthly-membership":
            root = Path(current).parent
            member = safe_path(root, f"monthly-membership/{filename}")
            preflight = safe_path(root, f"binding-preflight/preflight-{PREFLIGHT_SHA}.json")
            if member.is_file() and preflight.is_file():
                candidates.append(root)
    if len(candidates) != 1:
        raise MCFError("exactly one accepted evidence root required; supply --evidence-root if ambiguous")
    return candidates[0]


def inventory_reference(pc_root: Path) -> str:
    guard_root(pc_root)
    folder = safe_path(pc_root, "bootstrap")
    references = set()
    for path in sorted(folder.glob("bootstrap-*.json")):
        doc, raw = read_json(pc_root, str(path.relative_to(pc_root)))
        from .models import digest
        if (doc.get("schema") != "AF-01C-PC-BOOTSTRAP/1" or doc.get("state") != "BOOTSTRAPPED"
                or path.name != f"bootstrap-{digest(doc)}.json" or canonical(doc) != raw):
            raise MCFError("invalid AF-01C bootstrap identity")
        reference = doc.get("inventory_ref")
        safe_path(pc_root, reference)
        references.add(reference)
    if len(references) != 1:
        raise MCFError("exactly one bound AF-01C inventory reference required")
    return references.pop()


def prepare(*, pc_root: Path, search_root: Path, output_root: Path,
            evidence_root: Path | None = None) -> dict:
    evidence = evidence_root or discover_evidence(search_root)
    guard_root(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    materialized = materialize(
        pc_root=pc_root, evidence_root=evidence, output_root=output_root,
        plan_relative=f"plans/plan-{EXPECTED_PLAN_SHA256}.json",
        inventory_relative=inventory_reference(pc_root),
    )
    frozen = freeze_input(evidence_root=evidence, runtime_root=output_root,
                          index_relative=materialized["artifact"],
                          expected_index_sha256=materialized["index_sha256"])
    reader = FrozenRunnerInput(output_root, frozen["artifact"], frozen["runner_input_sha256"])
    reconcile_datasets(reader.root, reader._doc["runtime_index"])
    from .production_runtime import ProductionRuntime
    ProductionRuntime.from_frozen_input(reader)
    return {"status": "VPS_RUNTIME_DATA_AND_RUNNER_INPUT_VERIFIED_NO_PERFORMANCE",
            "evidence_root": str(evidence), "runtime_root": str(output_root),
            "materialization": materialized, "runner_input": frozen,
            "performance_authorized": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pc-root", type=Path, default=Path("/var/lib/yatl/research/opportunity-data-pc"))
    parser.add_argument("--search-root", type=Path, default=Path("/var/lib/yatl/research"))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(prepare(**vars(args)), sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "VPS_INPUT_PREPARATION_BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
