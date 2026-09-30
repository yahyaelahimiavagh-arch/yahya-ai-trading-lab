"""Metadata-only IB-002 pre-outcome multiplicity manifest CLI.

This command reads only frozen candidate governance/code metadata. It never runs
candidate performance and never opens Fresh OOS, recent reserve, P10 or live state.
"""
from __future__ import annotations

import argparse
import json

from .models import MCFError
from .production_generator import freeze_executable_generation
from .production_rules import BLOCKED_FAMILIES
from .statistical_guard import build_preoutcome_multiplicity_manifest

EXPECTED_EXECUTABLE_COUNT = 6852


def build_manifest() -> dict:
    frozen = freeze_executable_generation(BLOCKED_FAMILIES)
    summary = frozen["summary"]
    if (
        summary.get("generation_id") != "MCF-PROD-001"
        or summary.get("state") != "PRE_OUTCOME_EXECUTABLE_SET_FROZEN"
        or summary.get("executable_candidate_count") != EXPECTED_EXECUTABLE_COUNT
    ):
        raise MCFError("IB-002 requires exact frozen MCF-PROD-001 executable generation")
    graph = frozen.get("neighbor_graph", {}).get("graph")
    if not isinstance(graph, dict):
        raise MCFError("IB-002 requires exact frozen parameter-neighbor graph")
    manifest = build_preoutcome_multiplicity_manifest(
        frozen["executable"],
        neighbor_graph=graph,
        expected_candidate_count=EXPECTED_EXECUTABLE_COUNT,
    )
    return {
        **manifest,
        "generation_id": "MCF-PROD-001",
        "candidate_ledger_sha256": summary["candidate_ledger_sha256"],
        "neighbor_graph_sha256": summary["neighbor_graph_sha256"],
        "executable_freeze_sha256": summary["freeze_sha256"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze-manifest",))
    args = parser.parse_args(argv)
    try:
        if args.command == "freeze-manifest":
            print(json.dumps(build_manifest(), sort_keys=True))
            return 0
        raise MCFError("unsupported IB-002 command")
    except (MCFError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({
            "status": "IB_002_PREOUTCOME_BLOCKED",
            "reason": str(exc),
            "performance_read": False,
            "fresh_oos_read": False,
            "recent_reserve_read": False,
            "p10_read": False,
            "p10_write": False,
            "live_authorized": False,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
