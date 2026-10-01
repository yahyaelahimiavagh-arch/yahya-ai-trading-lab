"""Single frozen ninth-member memory diagnostic. Separate runtime approval required.

No benchmark loop, distributed coordinator, result writer, or economics output.
Linux-only worker telemetry uses a dedicated inherited log descriptor. Raw
stdout/stderr and core dumps are suppressed; only validated checkpoints persist.
"""
from __future__ import annotations

import argparse
import gc
import json
import math
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import time

from .models import MCFError, canonical, digest, guard_root, safe_path
from .production_capacity_benchmark import SAFETY, _selection_identity, select_benchmark_candidates
from .production_generator import freeze_executable_generation
from .production_memory_telemetry import STAGES, engineering_telemetry, memory_stage
from .production_rules import BLOCKED_FAMILIES
from .production_worker_runner import current_git_sha

SCHEMA = "MCF_SINGLE_CANDIDATE_MEMORY_DIAGNOSTIC/1.0.0"
AUTH_SCHEMA = "MCF_SINGLE_CANDIDATE_MEMORY_AUTHORIZATION/1.0.0"
SCOPE = "MCF-PROD-001-SINGLE-CANDIDATE-PEAK-MEMORY-DIAGNOSTIC"
CHECKPOINT_KEYS = frozenset({
    "stage", "phase", "rss_kib", "peak_rss_kib", "elapsed_seconds", "pid",
    "candidate_id", "candidate_spec_sha256", "runner_input_sha256", "git_sha",
})
MAX_LINE = 4096
MAX_CHECKPOINTS = 64


def target_identity() -> dict:
    # Same production generator and unchanged benchmark selection; no data read.
    freeze = freeze_executable_generation(BLOCKED_FAMILIES)
    if (len(freeze["executable"]) != 6852
            or freeze["summary"]["state"] != "PRE_OUTCOME_EXECUTABLE_SET_FROZEN"):
        raise MCFError("diagnostic frozen inventory mismatch")
    selected = select_benchmark_candidates(freeze["executable"])
    row = selected[8]
    return {"candidate_id": row["candidate_id"],
            "candidate_spec_sha256": row["candidate_spec_sha256"],
            "benchmark_selection_sha256": _selection_identity(selected)}


def _hex(value, width):
    return isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{width}}}", value) is not None


def identities(runner_sha, git_sha):
    if not _hex(runner_sha, 64) or not _hex(git_sha, 40):
        raise MCFError("diagnostic requires exact input/Git identities")
    target = target_identity()
    return {k: target[k] for k in ("candidate_id", "candidate_spec_sha256")} | {
        "runner_input_sha256": runner_sha, "git_sha": git_sha,
    }


def validate_authorization(doc, identity):
    target = target_identity()
    expected = {"schema": AUTH_SCHEMA, "scope": SCOPE, "authorized": True,
                "candidate_position": 9, "candidate_count": 1,
                "benchmark_selection_sha256": target["benchmark_selection_sha256"],
                **identity, "safety": dict(SAFETY)}
    if not isinstance(doc, dict) or set(doc) != set(expected) | {"authorization_sha256"}:
        raise MCFError("diagnostic authorization fields rejected")
    if any(doc[k] != v or type(doc[k]) is not type(v) for k, v in expected.items()):
        raise MCFError("diagnostic authorization boundary rejected")
    if canonical(doc["safety"]) != canonical(SAFETY) or doc["authorization_sha256"] != digest(expected):
        raise MCFError("diagnostic authorization identity/safety rejected")


def load_authorization(path, identity):
    guard_root(path)
    raw = path.read_bytes()
    doc = json.loads(raw)
    if canonical(doc) != raw:
        raise MCFError("diagnostic authorization must be canonical")
    validate_authorization(doc, identity)


def validate_checkpoint(row, identity, pid=None):
    if not isinstance(row, dict) or set(row) != CHECKPOINT_KEYS:
        raise MCFError("diagnostic checkpoint fields rejected")
    if any(row[k] != v for k, v in identity.items()):
        raise MCFError("diagnostic checkpoint identity rejected")
    if row["stage"] not in STAGES or row["phase"] not in ("begin", "end"):
        raise MCFError("diagnostic checkpoint stage rejected")
    for key in ("rss_kib", "peak_rss_kib", "pid"):
        if type(row[key]) is not int or row[key] <= 0:
            raise MCFError("diagnostic checkpoint integer rejected")
    if row["peak_rss_kib"] < row["rss_kib"] or (pid is not None and row["pid"] != pid):
        raise MCFError("diagnostic checkpoint process rejected")
    elapsed = row["elapsed_seconds"]
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise MCFError("diagnostic checkpoint time rejected")
    return row


class CheckpointSink:
    def __init__(self, stream, identity):
        self.stream, self.identity = stream, identity
        self.started = time.monotonic()

    def __call__(self, stage, phase):
        fields = {}
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith(("VmRSS:", "VmHWM:")):
                key, value, unit = line.split()
                if unit != "kB":
                    raise MCFError("diagnostic proc units rejected")
                fields[key[:-1]] = int(value)
        rss = fields["VmRSS"]
        row = {**self.identity, "stage": stage, "phase": phase, "rss_kib": rss,
               "peak_rss_kib": max(rss, fields["VmHWM"]), "pid": os.getpid(),
               "elapsed_seconds": round(time.monotonic() - self.started, 6)}
        validate_checkpoint(row, self.identity)
        self.stream.write(canonical(row).decode())
        self.stream.flush()


def execute_worker(args, stream):
    """Never called by preflight or tests with real Development input."""
    from .production_runner_input import FrozenRunnerInput
    from .production_runtime import ProductionRuntime
    identity = identities(args.expected_input_sha256, args.expected_git_sha)
    if current_git_sha() != args.expected_git_sha:
        raise MCFError("diagnostic Git mismatch")
    load_authorization(args.authorization, identity)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    with engineering_telemetry(CheckpointSink(stream, identity)):
        with memory_stage("frozen_input_admission"):
            reader = FrozenRunnerInput(args.runtime_root, args.input_relative, args.expected_input_sha256)
        with memory_stage("runtime_initialization"):
            runtime = ProductionRuntime.from_frozen_input(reader)
        try:
            result = runtime.run(identity["candidate_id"], director_authorized=True)
            with memory_stage("result_discard"):
                if (result.get("candidate_id") != identity["candidate_id"]
                        or result.get("candidate_spec_sha256") != identity["candidate_spec_sha256"]):
                    raise MCFError("diagnostic runtime identity rejected")
                del result  # no economics projection, serialization, or writer
        finally:
            with memory_stage("cleanup"):
                runtime.release_transient_features()
                del runtime, reader
                gc.collect()


class CheckpointJournal:
    """Validate BEFORE append; never store raw child text, even on failure."""
    def __init__(self, stream, identity, pid):
        self.stream, self.identity, self.pid = stream, identity, pid
        self.stack = []
        self.last = None
        self.last_completed = None
        self.count = 0
        self.elapsed = 0.0
        self.peak = 0
        self.completed = set()
        self.stage_index = -1

    def accept(self, row):
        validate_checkpoint(row, self.identity, self.pid)
        if self.count >= MAX_CHECKPOINTS or row["elapsed_seconds"] < self.elapsed or row["peak_rss_kib"] < self.peak:
            raise MCFError("diagnostic stream bounds rejected")
        stage, phase = row["stage"], row["phase"]
        if phase == "begin":
            if stage in self.completed or stage in self.stack:
                raise MCFError("diagnostic stage repetition rejected")
            index = STAGES.index(stage)
            if index <= self.stage_index:
                raise MCFError("diagnostic stage progression rejected")
            self.stage_index = index
            self.stack.append(stage)
        else:
            if not self.stack or self.stack[-1] != stage:
                raise MCFError("diagnostic stage order rejected")
            self.stack.pop()
            self.completed.add(stage)
            self.last_completed = stage
        self.stream.write(canonical(row).decode())
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.last = dict(row)
        self.count += 1
        self.elapsed, self.peak = row["elapsed_seconds"], row["peak_rss_kib"]

    def summary(self, returncode, rejected=False):
        signal = -returncode if returncode < 0 else (9 if returncode == 137 else None)
        complete = (not rejected and returncode == 0 and not self.stack
                    and set(STAGES) - {"liquidity_percentiles"} <= self.completed)
        status = ("DIAGNOSTIC_BOUNDARY_REJECTED" if rejected else
                  "DIAGNOSTIC_COMPLETE_NO_SELECTION" if complete else "DIAGNOSTIC_INCOMPLETE")
        return {"schema": SCHEMA, "status": status, **self.identity,
                "last_checkpoint": self.last, "last_completed_stage": self.last_completed,
                "active_stage": self.stack[-1] if self.stack else None,
                "child_returncode": returncode,
                "child_exit_code": 128 + signal if returncode < 0 else returncode,
                "child_signal": signal,
                "termination": "SIGKILL_OR_EXIT_137_OOM_UNCONFIRMED" if signal == 9 else
                               "OTHER_ABNORMAL_EXIT" if returncode != 0 else "NORMAL_EXIT",
                "diagnostic_completed": complete,
                "candidate_performance_exposed": False, "performance_artifacts_written": False,
                "selection_authorized": False, "full_batch_authorized": False,
                "benchmark_retry_authorized": False, "safety": dict(SAFETY)}


def supervise(command_builder, identity, output_root):
    guard_root(output_root)
    # Fresh directory prevents overwrite/retry from destroying incident evidence.
    output_root.mkdir(parents=True, exist_ok=False)
    log_path = safe_path(output_root, "checkpoints.jsonl")
    read_fd, write_fd = os.pipe()
    child = None
    try:
        child = subprocess.Popen(command_builder(write_fd), pass_fds=(write_fd,),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(write_fd)
        write_fd = None
        with os.fdopen(read_fd, "r", encoding="utf-8") as channel, log_path.open("x", encoding="utf-8") as log:
            read_fd = None
            journal = CheckpointJournal(log, identity, child.pid)
            rejected = False
            try:
                while True:
                    line = channel.readline(MAX_LINE + 1)
                    if not line:
                        break
                    if len(line) > MAX_LINE or not line.endswith("\n"):
                        raise MCFError("diagnostic log framing rejected")
                    journal.accept(json.loads(line))
            except (ValueError, TypeError, KeyError, UnicodeError, OSError):
                rejected = True
                child.kill()
            rc = child.wait()
            result = journal.summary(rc, rejected)
        with safe_path(output_root, "summary.json").open("xb") as out:
            out.write(canonical(result)); out.flush(); os.fsync(out.fileno())
        return result
    finally:
        if child is not None and child.poll() is None:
            child.kill(); child.wait()
        for fd in (read_fd, write_fd):
            if fd is not None:
                os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "diagnose", "worker"))
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--input-relative", required=True)
    parser.add_argument("--expected-input-sha256", required=True)
    parser.add_argument("--expected-git-sha", required=True)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--checkpoint-fd", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        identity = identities(args.expected_input_sha256, args.expected_git_sha)
        if current_git_sha() != args.expected_git_sha:
            raise MCFError("diagnostic Git mismatch")
        guard_root(args.runtime_root)
        safe_path(args.runtime_root, args.input_relative)
        if args.input_relative != f"runner-input/input-{args.expected_input_sha256}.json":
            raise MCFError("diagnostic input path mismatch")
        if args.command == "preflight":
            if args.authorization or args.output_root or args.checkpoint_fd is not None:
                raise MCFError("preflight rejects execution options")
            print(json.dumps({"schema": SCHEMA, "status": "PREFLIGHT_METADATA_ONLY_NO_PERFORMANCE",
                              **identity, **target_identity(), "safety": SAFETY,
                              "runtime_authorized": False, "benchmark_retry_authorized": False,
                              "full_batch_authorized": False}, sort_keys=True))
            return 0
        if args.authorization is None:
            raise MCFError("separate Director diagnostic authorization required")
        load_authorization(args.authorization, identity)
        if args.command == "worker":
            if args.checkpoint_fd is None or args.checkpoint_fd <= 2 or args.output_root is not None:
                raise MCFError("worker requires isolated engineering channel")
            with os.fdopen(args.checkpoint_fd, "w", encoding="utf-8", buffering=1) as stream:
                execute_worker(args, stream)
            return 0
        if args.output_root is None or args.checkpoint_fd is not None:
            raise MCFError("diagnose requires fresh output directory")
        def command(fd):
            return [sys.executable, "-m", __spec__.name, "worker",
                    "--runtime-root", str(args.runtime_root), "--input-relative", args.input_relative,
                    "--expected-input-sha256", args.expected_input_sha256,
                    "--expected-git-sha", args.expected_git_sha,
                    "--authorization", str(args.authorization), "--checkpoint-fd", str(fd)]
        result = supervise(command, identity, args.output_root)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["diagnostic_completed"] else 2
    except Exception:
        # Never forward arbitrary exception text (which may contain economics).
        if args.command != "worker":
            print(json.dumps({"schema": SCHEMA, "status": "DIAGNOSTIC_BLOCKED",
                              "runtime_authorized": False, "selection_authorized": False,
                              "full_batch_authorized": False, "benchmark_retry_authorized": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
