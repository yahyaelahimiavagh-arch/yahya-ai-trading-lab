"""Blind capacity benchmark for the frozen MCF-PROD-001 Development runtime.

This command deliberately exposes no candidate economics, trade counts, returns,
rankings, or survivor state. It runs a fixed pre-outcome stratified subset only
to measure operational throughput and memory before a separate full-batch gate.
"""
from __future__ import annotations

import argparse
import gc
import json
import resource
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .models import MCFError, digest
from .production_runner_input import FrozenRunnerInput
from .production_runtime import ProductionRuntime

BENCHMARK_ID = "MCF-PROD-001-CAPACITY-BENCHMARK-001"
AUTHORIZATION_TOKEN = BENCHMARK_ID
BENCHMARK_CANDIDATE_COUNT = 24
EXPECTED_EXECUTABLE_COUNT = 6852
WORKER_SCHEMA = "MCF_PROD_CAPACITY_BENCHMARK_WORKER/1.0.0"

SAFETY = {
    "paper_research_only": True,
    "live_master_lock": "OFF",
    "futures": False,
    "leverage": False,
    "short": False,
    "live": False,
    "order_endpoint": False,
    "ai_direct_execution": False,
    "fresh_oos_read": False,
    "recent_reserve_read": False,
    "p10_read": False,
    "p10_write": False,
    "p11_locked": True,
    "selection_authorized": False,
    "full_batch_authorized": False,
}


def select_benchmark_candidates(
    executable: Sequence[Mapping[str, object]],
    count: int = BENCHMARK_CANDIDATE_COUNT,
) -> tuple[Mapping[str, object], ...]:
    """Choose a deterministic family/timeframe round-robin subset without outcomes."""
    if type(count) is not int or count <= 0:
        raise MCFError("invalid capacity benchmark count")
    buckets: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    seen = set()
    for row in executable:
        cid = str(row.get("candidate_id", ""))
        family = str(row.get("family", ""))
        timeframe = str(row.get("timeframe", ""))
        spec = str(row.get("candidate_spec_sha256", ""))
        if not cid or not family or timeframe not in {"15m", "1h", "4h"} or len(spec) != 64:
            raise MCFError("invalid frozen candidate in capacity benchmark inventory")
        if cid in seen:
            raise MCFError("duplicate frozen candidate in capacity benchmark inventory")
        seen.add(cid)
        buckets[(family, timeframe)].append(row)
    if len(executable) < count or not buckets:
        raise MCFError("insufficient frozen candidates for capacity benchmark")
    for rows in buckets.values():
        rows.sort(key=lambda row: str(row["candidate_id"]))
    keys = tuple(sorted(buckets))
    offsets = {key: 0 for key in keys}
    selected = []
    while len(selected) < count:
        advanced = False
        for key in keys:
            offset = offsets[key]
            rows = buckets[key]
            if offset >= len(rows):
                continue
            selected.append(rows[offset])
            offsets[key] = offset + 1
            advanced = True
            if len(selected) == count:
                break
        if not advanced:
            raise MCFError("capacity benchmark selection exhausted unexpectedly")
    return tuple(selected)


def _selection_identity(selected: Sequence[Mapping[str, object]]) -> str:
    return digest([
        {
            "candidate_id": str(row["candidate_id"]),
            "candidate_spec_sha256": str(row["candidate_spec_sha256"]),
            "family": str(row["family"]),
            "timeframe": str(row["timeframe"]),
        }
        for row in selected
    ])


def run_capacity_benchmark(
    runtime: ProductionRuntime,
    runner_input_sha256: str,
    *,
    clock: Callable[[], float] = time.monotonic,
    usage: Callable[[], object] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Run the fixed blind subset and return capacity metrics only."""
    executable = tuple(runtime.executable_freeze.get("executable", ()))
    summary = runtime.executable_freeze.get("summary", {})
    if (
        summary.get("generation_id") != "MCF-PROD-001"
        or summary.get("state") != "PRE_OUTCOME_EXECUTABLE_SET_FROZEN"
        or summary.get("executable_candidate_count") != EXPECTED_EXECUTABLE_COUNT
        or len(executable) != EXPECTED_EXECUTABLE_COUNT
    ):
        raise MCFError("capacity benchmark requires the exact frozen executable generation")
    if not isinstance(runner_input_sha256, str) or len(runner_input_sha256) != 64:
        raise MCFError("capacity benchmark requires pinned runner input identity")

    selected = select_benchmark_candidates(executable)
    selection_sha = _selection_identity(selected)
    usage_fn = usage or (lambda: resource.getrusage(resource.RUSAGE_SELF))
    before_usage = usage_fn()
    wall_start = clock()
    bucket_seconds: dict[tuple[str, str], float] = defaultdict(float)
    bucket_counts: dict[tuple[str, str], int] = defaultdict(int)

    for position, candidate in enumerate(selected, 1):
        started = clock()
        try:
            result = runtime.run(str(candidate["candidate_id"]), director_authorized=True)
            elapsed = max(0.0, clock() - started)
            if (
                result.get("candidate_id") != candidate["candidate_id"]
                or result.get("candidate_spec_sha256") != candidate["candidate_spec_sha256"]
            ):
                raise MCFError("capacity benchmark runtime result identity mismatch")
            key = (str(candidate["family"]), str(candidate["timeframe"]))
            bucket_seconds[key] += elapsed
            bucket_counts[key] += 1
            del result
        finally:
            runtime.release_transient_features()
            gc.collect()
        if progress is not None:
            progress(position, len(selected))

    wall_seconds = max(0.0, clock() - wall_start)
    after_usage = usage_fn()
    bucket_rows = [
        {
            "family": family,
            "timeframe": timeframe,
            "candidate_count": bucket_counts[(family, timeframe)],
            "wall_seconds": round(bucket_seconds[(family, timeframe)], 6),
        }
        for family, timeframe in sorted(bucket_counts)
    ]

    return {
        "schema": "MCF_PROD_CAPACITY_BENCHMARK/1.0.0",
        "benchmark_id": BENCHMARK_ID,
        "status": "CAPACITY_BENCHMARK_COMPLETE_NO_SELECTION",
        "runner_input_sha256": runner_input_sha256,
        "executable_candidate_count": EXPECTED_EXECUTABLE_COUNT,
        "benchmark_candidate_count": len(selected),
        "benchmark_selection_sha256": selection_sha,
        "family_timeframe_bucket_count": len(bucket_rows),
        "wall_seconds": round(wall_seconds, 6),
        "cpu_user_seconds": round(max(0.0, after_usage.ru_utime - before_usage.ru_utime), 6),
        "cpu_system_seconds": round(max(0.0, after_usage.ru_stime - before_usage.ru_stime), 6),
        "peak_rss_kib": int(after_usage.ru_maxrss),
        "bucket_timings": bucket_rows,
        "candidate_performance_exposed": False,
        "performance_artifacts_written": False,
        "selection_authorized": False,
        "full_batch_authorized": False,
        "safety": SAFETY,
    }


def _current_rss_kib() -> int | None:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _progress(position: int, total: int) -> None:
    percent = 100.0 * position / total
    rss = _current_rss_kib()
    suffix = "" if rss is None else f" RSS_KIB={rss}"
    print(
        f"CAPACITY_BENCHMARK_PROGRESS={position}/{total} ({percent:.1f}%){suffix}",
        file=sys.stderr,
        flush=True,
    )


def _fixed_selection(runtime: ProductionRuntime) -> tuple[Mapping[str, object], ...]:
    executable = tuple(runtime.executable_freeze.get("executable", ()))
    summary = runtime.executable_freeze.get("summary", {})
    if (
        summary.get("generation_id") != "MCF-PROD-001"
        or summary.get("state") != "PRE_OUTCOME_EXECUTABLE_SET_FROZEN"
        or summary.get("executable_candidate_count") != EXPECTED_EXECUTABLE_COUNT
        or len(executable) != EXPECTED_EXECUTABLE_COUNT
    ):
        raise MCFError("capacity benchmark requires the exact frozen executable generation")
    return select_benchmark_candidates(executable)


def _run_worker(
    runtime: ProductionRuntime,
    candidate_id: str,
    candidate_spec_sha256: str,
    *,
    clock: Callable[[], float] = time.monotonic,
    usage: Callable[[], object] | None = None,
) -> dict:
    """Run exactly one member of the fixed blind subset and discard its economics."""
    selected = _fixed_selection(runtime)
    allowed = {str(row["candidate_id"]): row for row in selected}
    candidate = allowed.get(candidate_id)
    if candidate is None or str(candidate["candidate_spec_sha256"]) != candidate_spec_sha256:
        raise MCFError("capacity worker candidate outside fixed blind benchmark selection")
    usage_fn = usage or (lambda: resource.getrusage(resource.RUSAGE_SELF))
    before_usage = usage_fn()
    started = clock()
    try:
        result = runtime.run(candidate_id, director_authorized=True)
        elapsed = max(0.0, clock() - started)
        if (
            result.get("candidate_id") != candidate_id
            or result.get("candidate_spec_sha256") != candidate_spec_sha256
        ):
            raise MCFError("capacity benchmark runtime result identity mismatch")
        del result
    finally:
        runtime.release_transient_features()
        gc.collect()
    after_usage = usage_fn()
    return {
        "schema": WORKER_SCHEMA,
        "status": "CAPACITY_BENCHMARK_WORKER_COMPLETE_NO_SELECTION",
        "candidate_id": candidate_id,
        "candidate_spec_sha256": candidate_spec_sha256,
        "wall_seconds": round(elapsed, 6),
        "cpu_user_seconds": round(max(0.0, after_usage.ru_utime - before_usage.ru_utime), 6),
        "cpu_system_seconds": round(max(0.0, after_usage.ru_stime - before_usage.ru_stime), 6),
        "peak_rss_kib": int(after_usage.ru_maxrss),
        "candidate_performance_exposed": False,
        "performance_artifacts_written": False,
    }


_WORKER_KEYS = {
    "schema",
    "status",
    "candidate_id",
    "candidate_spec_sha256",
    "wall_seconds",
    "cpu_user_seconds",
    "cpu_system_seconds",
    "peak_rss_kib",
    "candidate_performance_exposed",
    "performance_artifacts_written",
}


def _validate_worker_result(result: object, candidate: Mapping[str, object]) -> dict:
    if not isinstance(result, dict) or set(result) != _WORKER_KEYS:
        raise MCFError("isolated capacity worker returned unexpected fields")
    if (
        result.get("schema") != WORKER_SCHEMA
        or result.get("status") != "CAPACITY_BENCHMARK_WORKER_COMPLETE_NO_SELECTION"
        or result.get("candidate_id") != candidate["candidate_id"]
        or result.get("candidate_spec_sha256") != candidate["candidate_spec_sha256"]
        or result.get("candidate_performance_exposed") is not False
        or result.get("performance_artifacts_written") is not False
    ):
        raise MCFError("isolated capacity worker result boundary mismatch")
    for key in ("wall_seconds", "cpu_user_seconds", "cpu_system_seconds"):
        value = result.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise MCFError("isolated capacity worker timing invalid")
    rss = result.get("peak_rss_kib")
    if type(rss) is not int or rss <= 0:
        raise MCFError("isolated capacity worker RSS invalid")
    return result


def run_capacity_benchmark_isolated(
    runtime: ProductionRuntime,
    runner_input_sha256: str,
    *,
    worker: Callable[[Mapping[str, object]], dict],
    clock: Callable[[], float] = time.monotonic,
    progress: Callable[[int, int, int], None] | None = None,
) -> dict:
    """Aggregate capacity-only results from one fresh OS process per candidate."""
    if not isinstance(runner_input_sha256, str) or len(runner_input_sha256) != 64:
        raise MCFError("capacity benchmark requires pinned runner input identity")
    selected = _fixed_selection(runtime)
    wall_start = clock()
    bucket_seconds: dict[tuple[str, str], float] = defaultdict(float)
    bucket_counts: dict[tuple[str, str], int] = defaultdict(int)
    cpu_user = 0.0
    cpu_system = 0.0
    peak_rss = 0

    for position, candidate in enumerate(selected, 1):
        result = _validate_worker_result(worker(candidate), candidate)
        key = (str(candidate["family"]), str(candidate["timeframe"]))
        bucket_seconds[key] += float(result["wall_seconds"])
        bucket_counts[key] += 1
        cpu_user += float(result["cpu_user_seconds"])
        cpu_system += float(result["cpu_system_seconds"])
        peak_rss = max(peak_rss, int(result["peak_rss_kib"]))
        if progress is not None:
            progress(position, len(selected), int(result["peak_rss_kib"]))

    bucket_rows = [
        {
            "family": family,
            "timeframe": timeframe,
            "candidate_count": bucket_counts[(family, timeframe)],
            "wall_seconds": round(bucket_seconds[(family, timeframe)], 6),
        }
        for family, timeframe in sorted(bucket_counts)
    ]
    return {
        "schema": "MCF_PROD_CAPACITY_BENCHMARK/1.0.0",
        "benchmark_id": BENCHMARK_ID,
        "status": "CAPACITY_BENCHMARK_COMPLETE_NO_SELECTION",
        "runner_input_sha256": runner_input_sha256,
        "executable_candidate_count": EXPECTED_EXECUTABLE_COUNT,
        "benchmark_candidate_count": len(selected),
        "benchmark_selection_sha256": _selection_identity(selected),
        "family_timeframe_bucket_count": len(bucket_rows),
        "wall_seconds": round(max(0.0, clock() - wall_start), 6),
        "cpu_user_seconds": round(cpu_user, 6),
        "cpu_system_seconds": round(cpu_system, 6),
        "peak_rss_kib": peak_rss,
        "bucket_timings": bucket_rows,
        "candidate_performance_exposed": False,
        "performance_artifacts_written": False,
        "selection_authorized": False,
        "full_batch_authorized": False,
        "safety": SAFETY,
    }


def _isolated_progress(position: int, total: int, worker_peak_rss_kib: int) -> None:
    percent = 100.0 * position / total
    print(
        f"CAPACITY_BENCHMARK_PROGRESS={position}/{total} "
        f"({percent:.1f}%) WORKER_PEAK_RSS_KIB={worker_peak_rss_kib}",
        file=sys.stderr,
        flush=True,
    )


def _subprocess_worker(
    candidate: Mapping[str, object],
    *,
    runtime_root: Path,
    input_relative: str,
    expected_input_sha256: str,
    director_authorization: str,
) -> dict:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "research.mass_candidate_factory.production_capacity_benchmark",
            "candidate-worker",
            "--runtime-root", str(runtime_root),
            "--input-relative", input_relative,
            "--expected-input-sha256", expected_input_sha256,
            "--director-authorization", director_authorization,
            "--candidate-id", str(candidate["candidate_id"]),
            "--candidate-spec-sha256", str(candidate["candidate_spec_sha256"]),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        code = 128 + (-completed.returncode) if completed.returncode < 0 else completed.returncode
        raise MCFError(f"isolated capacity worker failed with exit code {code}")
    try:
        return json.loads(completed.stdout)
    except (TypeError, ValueError) as exc:
        raise MCFError("isolated capacity worker returned invalid JSON") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("benchmark", "candidate-worker"))
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--input-relative", required=True)
    parser.add_argument("--expected-input-sha256", required=True)
    parser.add_argument("--director-authorization", required=True)
    parser.add_argument("--candidate-id")
    parser.add_argument("--candidate-spec-sha256")
    args = parser.parse_args(argv)
    try:
        if args.director_authorization != AUTHORIZATION_TOKEN:
            raise MCFError("capacity benchmark Director authorization token mismatch")
        reader = FrozenRunnerInput(
            args.runtime_root,
            args.input_relative,
            args.expected_input_sha256,
        )
        runtime = ProductionRuntime.from_frozen_input(reader)
        if args.command == "candidate-worker":
            if not args.candidate_id or not args.candidate_spec_sha256:
                raise MCFError("capacity worker requires pinned candidate identity")
            result = _run_worker(runtime, args.candidate_id, args.candidate_spec_sha256)
        else:
            if args.candidate_id or args.candidate_spec_sha256:
                raise MCFError("capacity benchmark does not accept candidate override")
            result = run_capacity_benchmark_isolated(
                runtime,
                args.expected_input_sha256,
                worker=lambda candidate: _subprocess_worker(
                    candidate,
                    runtime_root=args.runtime_root,
                    input_relative=args.input_relative,
                    expected_input_sha256=args.expected_input_sha256,
                    director_authorization=args.director_authorization,
                ),
                progress=_isolated_progress,
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({
            "status": "CAPACITY_BENCHMARK_BLOCKED",
            "reason": str(exc),
            "selection_authorized": False,
            "full_batch_authorized": False,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
