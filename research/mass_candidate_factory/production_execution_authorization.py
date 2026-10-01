"""Freeze a Director-controlled authorization for the 6,852 Development run.

This module never executes candidate performance. It only emits an immutable
authorization artifact after verifying:
- the exact distributed plan;
- the exact refrozen runner input;
- the exact accepted Git commit;
- the blind 24-candidate capacity benchmark contract and raw SHA-256.

Selection/promotion, Fresh OOS, recent reserve, P10, Live, futures, leverage and
shorting remain explicitly unauthorized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .models import MCFError, canonical, digest, write_once
from .production_distributed import validate_plan
from .production_runner_input import FrozenRunnerInput
from .production_worker_runner import (
    AUTH_SCHEMA,
    AUTH_SCOPE,
    current_git_sha,
    validate_authorization,
)

DIRECTOR_TOKEN = "AUTHORIZE_MCF_PROD_001_DEVELOPMENT_FULL_6852"


def _load_canonical(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    doc = json.loads(raw)
    if not isinstance(doc, dict) or canonical(doc) != raw:
        raise MCFError("expected canonical JSON artifact")
    return doc, raw


def freeze_authorization(
    *,
    plan_path: Path,
    runtime_root: Path,
    runner_input_relative: str,
    runner_input_sha256: str,
    benchmark_path: Path,
    expected_git_sha: str,
    output: Path,
    director_token: str,
) -> dict:
    if director_token != DIRECTOR_TOKEN:
        raise MCFError("explicit Director full-run authorization token mismatch")

    plan, _ = _load_canonical(plan_path)
    validate_plan(plan)
    if plan.get("candidate_count") != 6852 or plan.get("batch_count") != 14:
        raise MCFError("full-run authorization requires exact 6,852/14 plan")

    actual_git = current_git_sha()
    if actual_git != expected_git_sha:
        raise MCFError("authorization Git HEAD mismatch")

    reader = FrozenRunnerInput(
        runtime_root,
        runner_input_relative,
        runner_input_sha256,
    )
    reader.assert_unchanged()

    # The accepted benchmark CLI emits ordinary sorted JSON, not canonical
    # compact JSON. Bind its exact original bytes; do not rewrite the evidence.
    benchmark_raw = benchmark_path.read_bytes()
    benchmark = json.loads(benchmark_raw)
    if not isinstance(benchmark, dict):
        raise MCFError("capacity benchmark must be a JSON object")
    if (
        benchmark.get("status") != "CAPACITY_BENCHMARK_COMPLETE_NO_SELECTION"
        or benchmark.get("runner_input_sha256") != runner_input_sha256
        or benchmark.get("executable_candidate_count") != 6852
        or benchmark.get("benchmark_candidate_count") != 24
        or benchmark.get("candidate_performance_exposed") is not False
        or benchmark.get("performance_artifacts_written") is not False
        or benchmark.get("selection_authorized") is not False
        or benchmark.get("full_batch_authorized") is not False
    ):
        raise MCFError("capacity benchmark is not acceptable for full-run authorization")

    benchmark_sha = hashlib.sha256(benchmark_raw).hexdigest()
    base = {
        "schema": AUTH_SCHEMA,
        "scope": AUTH_SCOPE,
        "authorized": True,
        "plan_sha256": plan["plan_sha256"],
        "runner_input_sha256": runner_input_sha256,
        "git_sha": expected_git_sha,
        "capacity_benchmark_sha256": benchmark_sha,
        "capacity_benchmark_candidate_count": 24,
        "candidate_count": 6852,
        "batch_count": 14,
        "max_concurrent_microshards_per_node": 1,
        "selection_authorized": False,
        "promotion_authorized": False,
        "fresh_oos_read": False,
        "recent_reserve_read": False,
        "p10_read": False,
        "p10_write": False,
        "live": False,
        "futures": False,
        "leverage": False,
        "short": False,
    }
    authorization = {**base, "authorization_sha256": digest(base)}
    validate_authorization(
        authorization,
        plan_sha256=str(plan["plan_sha256"]),
        runner_input_sha256=runner_input_sha256,
        git_sha=expected_git_sha,
    )
    write_once(output, canonical(authorization))
    return {
        "status": "FULL_6852_DEVELOPMENT_AUTHORIZATION_FROZEN",
        "authorization_sha256": authorization["authorization_sha256"],
        "capacity_benchmark_sha256": benchmark_sha,
        "plan_sha256": plan["plan_sha256"],
        "runner_input_sha256": runner_input_sha256,
        "git_sha": expected_git_sha,
        "max_concurrent_microshards_per_node": 1,
        "selection_authorized": False,
        "promotion_authorized": False,
        "output": str(output),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--runner-input-relative", required=True)
    parser.add_argument("--runner-input-sha256", required=True)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--expected-git-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--director-authorization", required=True)
    args = parser.parse_args(argv)
    try:
        result = freeze_authorization(
            plan_path=args.plan,
            runtime_root=args.runtime_root,
            runner_input_relative=args.runner_input_relative,
            runner_input_sha256=args.runner_input_sha256,
            benchmark_path=args.benchmark,
            expected_git_sha=args.expected_git_sha,
            output=args.output,
            director_token=args.director_authorization,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({
            "status": "FULL_6852_AUTHORIZATION_BLOCKED",
            "reason": str(exc),
            "performance_execution_authorized": False,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
