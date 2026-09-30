"""Freeze and consume an exact Development runner input; no performance CLI.

The frozen reader has no external-data fallback. All referenced files are under
one guarded output root, content addressed, and verified before feature use.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from research.crisis_lab.acquisition import _canonical_csv
from research.opportunity_data.models import sha256
from research.opportunity_data.storage import read_canonical

from .models import MCFError, canonical, digest, guard_root, safe_path, write_once
from .production import (
    MembershipSnapshot, ProductionCostPolicy, ProductionUniverseBinding,
    UNIVERSE_EVIDENCE_ID, freeze_digest,
)
from .production_features import ProductionBars
from .production_freeze import build_payloads
from .production_generator import freeze_executable_generation
from .production_rules import BLOCKED_FAMILIES
from .production_runtime_data import (
    BOUNDS, CLASSIFICATION_SHA, EXPECTED_PLAN_SHA256,
    EXPECTED_POPULATION_RECONCILIATION_SHA256, MEMBERSHIP_SHA, PREFLIGHT_SHA,
    SAFETY, TIMEFRAMES, VERSION as INDEX_VERSION, accepted_membership,
    derive_complete, full_gap_map, read_hashed, read_json, validate_development,
)

VERSION = "MCF_PRODUCTION_RUNNER_INPUT/1.0.0"
ROOT = Path(__file__).resolve().parents[2]
CODE_PATHS = (
    "research/mass_candidate_factory/production_runtime_data.py",
    "research/mass_candidate_factory/production_runner_input.py",
    "research/mass_candidate_factory/production_runtime.py",
    "research/mass_candidate_factory/production_features.py",
    "research/mass_candidate_factory/production.py",
    "research/mass_candidate_factory/production_rules.py",
    "research/opportunity_data/views.py",
    "research/opportunity_data/canonical.py",
)


def code_identity() -> dict:
    return {p: sha256((ROOT / p).read_bytes()) for p in CODE_PATHS}


def universe_binding(membership: dict, index: dict) -> ProductionUniverseBinding:
    binding = ProductionUniverseBinding(
        universe_evidence_id=UNIVERSE_EVIDENCE_ID,
        population_manifest_sha256=membership["population_reconciliation_sha256"],
        quality_index_sha256=index["index_sha256"],
        universe_policy_sha256=membership["universe_policy_sha256"],
        membership_snapshots=tuple(MembershipSnapshot(
            x["effective_ms"], tuple(x["selected_symbols"]), x["membership_sha256"]
        ) for x in membership["monthly_memberships"]),
    )
    binding.validate()
    return binding


def validate_index(index: dict, membership: dict) -> None:
    base = {k: v for k, v in index.items() if k != "index_sha256"}
    if (digest(base) != index.get("index_sha256") or index.get("schema") != INDEX_VERSION
            or index.get("generation_id") != "MCF-PROD-001"
            or index.get("state") != "RUNTIME_DATA_MATERIALIZED_BEFORE_PERFORMANCE"
            or index.get("safety") != SAFETY or index.get("evidence_bounds") != BOUNDS
            or tuple(index.get("timeframes", ())) != TIMEFRAMES):
        raise MCFError("unregistered runtime index boundary")
    identities = {"membership_freeze_sha256": MEMBERSHIP_SHA,
                  "source_preflight_sha256": PREFLIGHT_SHA,
                  "classification_map_sha256": CLASSIFICATION_SHA,
                  "plan_sha256": EXPECTED_PLAN_SHA256,
                  "population_reconciliation_sha256": EXPECTED_POPULATION_RECONCILIATION_SHA256,
                  "universe_policy_sha256": membership["universe_policy_sha256"]}
    if any(index.get(k) != v for k, v in identities.items()):
        raise MCFError("runtime index provenance differs from accepted membership")
    union = tuple(membership["selected_union_symbols"])
    if tuple(index.get("selected_union_symbols", ())) != union:
        raise MCFError("runtime index contains an outside/missing union symbol")
    wanted = [(s, tf) for s in union for tf in TIMEFRAMES]
    rows = index.get("datasets", [])
    if ([(x.get("symbol"), x.get("timeframe")) for x in rows] != wanted
            or index.get("dataset_count") != len(wanted)):
        raise MCFError("runtime index dataset matrix mismatch")
    for row in rows:
        if (row.get("evidence_bounds") != BOUNDS
                or row.get("evidence_partition") != "DEVELOPMENT"
                or digest(row.get("source_15m_records")) != row.get("source_records_sha256")
                or row.get("row_count", 0) < 2):
            raise MCFError("runtime dataset provenance/count mismatch")
        prefix = f"runtime-data/{row['symbol']}/{row['timeframe']}"
        if (row.get("data_ref") != f"{prefix}/canonical-{row.get('content_sha256')}.csv"
                or row.get("gap_ref") != f"{prefix}/gaps-{row.get('gap_sha256')}.json"
                or row.get("dataset_id") != f"MCF-PROD-001/{row['symbol']}-{row['timeframe']}/{row.get('source_15m_sha256')}"):
            raise MCFError("runtime dataset path/identity mismatch")


def read_dataset(root: Path, row: dict):
    timeframe = row["timeframe"]
    if timeframe not in TIMEFRAMES:
        raise MCFError("unregistered runtime timeframe")
    data = read_canonical(root, row["data_ref"], row["content_sha256"])
    validate_development(data, timeframe)
    gap, raw = read_json(root, row["gap_ref"])
    if (sha256(raw) != row["gap_sha256"]
            or canonical(full_gap_map(data, row["symbol"], timeframe, row["dataset_id"])) != raw
            or len(data) != row["row_count"]
            or data[0].open_time_ms != row["first_time_ms"]
            or data[-1].open_time_ms != row["last_time_ms"]
            or gap["gap_count"] != row["gap_count"]
            or row["validity"] != ("PASS_WITH_GAPS" if gap["gap_count"] else "PASS_CONTIGUOUS")):
        raise MCFError("runtime data/coverage/gap reconciliation mismatch")
    return data


def reconcile_datasets(root: Path, index: dict) -> None:
    """Stream one symbol at a time; prove derived bytes and dropped bucket counts."""
    rows = index["datasets"]
    for offset in range(0, len(rows), 3):
        group = rows[offset:offset + 3]
        source = read_dataset(root, group[0])
        if sha256(_canonical_csv(source)) != group[0]["source_15m_sha256"]:
            raise MCFError("runtime source 15m hash mismatch")
        for row in group:
            actual = read_dataset(root, row)
            derived, dropped = derive_complete(source, row["symbol"], row["timeframe"], row["dataset_id"])
            if (actual != derived or dropped != row["incomplete_bucket_dropped_count"]
                    or row["source_15m_records"] != group[0]["source_15m_records"]
                    or row["source_15m_sha256"] != group[0]["source_15m_sha256"]):
                raise MCFError("runtime timeframe hides source gaps or changes derivation")


def freeze_input(*, evidence_root: Path, runtime_root: Path, index_relative: str,
                 expected_index_sha256: str) -> dict:
    guard_root(evidence_root)
    guard_root(runtime_root)
    membership = accepted_membership(evidence_root)
    index = read_hashed(runtime_root, index_relative, expected_index_sha256, "index_sha256")
    validate_index(index, membership)
    reconcile_datasets(runtime_root, index)
    candidates, _ = build_payloads()  # verifies all accepted 6,852 identity hashes
    executable = freeze_executable_generation(BLOCKED_FAMILIES)
    cost = ProductionCostPolicy()
    binding = universe_binding(membership, index)
    binding_sha, cost_sha = freeze_digest(binding, cost)
    base = {"schema": VERSION, "generation_id": "MCF-PROD-001",
            "state": "RUNNER_INPUT_FROZEN_BEFORE_PERFORMANCE",
            "membership": membership, "runtime_index": index,
            "executable_freeze_sha256": candidates["freeze_sha256"],
            "candidate_ledger_sha256": candidates["candidate_ledger_sha256"],
            "neighbor_graph_sha256": candidates["neighbor_graph_sha256"],
            "executable_object_sha256": digest(executable),
            "cost_policy": asdict(cost), "cost_policy_sha256": cost_sha,
            "evidence_binding_sha256": binding_sha,
            "evidence_bounds": BOUNDS, "allowed_timeframes": TIMEFRAMES,
            "runtime_code_sha256": code_identity(), "safety": SAFETY,
            "coverage_reconciled": True, "performance_authorized": False}
    doc = {**base, "runner_input_sha256": digest(base)}
    relative = f"runner-input/input-{doc['runner_input_sha256']}.json"
    write_once(safe_path(runtime_root, relative), canonical(doc))
    return {"status": doc["state"], "artifact": relative,
            "runner_input_sha256": doc["runner_input_sha256"],
            "dataset_count": index["dataset_count"], "safety": SAFETY,
            "performance_authorized": False}


class FrozenRunnerInput:
    """Reader for one pinned manifest; exposes only its admitted matrix."""

    def __init__(self, root: Path, relative: str, expected_sha256: str):
        self.root = guard_root(root)
        self.relative, self.expected_sha256 = relative, expected_sha256
        doc = read_hashed(self.root, relative, expected_sha256, "runner_input_sha256")
        if (relative != f"runner-input/input-{expected_sha256}.json"
                or doc.get("schema") != VERSION or doc.get("generation_id") != "MCF-PROD-001"
                or doc.get("state") != "RUNNER_INPUT_FROZEN_BEFORE_PERFORMANCE"
                or doc.get("safety") != SAFETY or doc.get("evidence_bounds") != BOUNDS
                or tuple(doc.get("allowed_timeframes", ())) != TIMEFRAMES
                or doc.get("coverage_reconciled") is not True
                or doc.get("performance_authorized") is not False
                or doc.get("runtime_code_sha256") != code_identity()):
            raise MCFError("runner input boundary/code/safety mismatch")
        membership = doc["membership"]
        base = {k: v for k, v in membership.items() if k != "freeze_sha256"}
        if membership.get("freeze_sha256") != MEMBERSHIP_SHA or digest(base) != MEMBERSHIP_SHA:
            raise MCFError("runner membership substitution")
        validate_index(doc["runtime_index"], membership)
        candidates, _ = build_payloads()
        for key in ("candidate_ledger_sha256", "neighbor_graph_sha256"):
            if doc.get(key) != candidates[key]:
                raise MCFError("runner candidate freeze substitution")
        if doc.get("executable_freeze_sha256") != candidates["freeze_sha256"]:
            raise MCFError("runner executable freeze substitution")
        self.binding = universe_binding(membership, doc["runtime_index"])
        self.cost_policy = ProductionCostPolicy(**doc["cost_policy"])
        binding_sha, cost_sha = freeze_digest(self.binding, self.cost_policy)
        if (binding_sha != doc["evidence_binding_sha256"]
                or cost_sha != doc["cost_policy_sha256"]
                or asdict(self.cost_policy) != asdict(ProductionCostPolicy())):
            raise MCFError("runner universe/cost binding mismatch")
        self._canonical_doc = canonical(doc)
        self._doc = doc
        self._rows = {(x["symbol"], x["timeframe"]): x for x in doc["runtime_index"]["datasets"]}

    def assert_unchanged(self) -> None:
        if safe_path(self.root, self.relative).read_bytes() != self._canonical_doc:
            raise MCFError("runner input changed after admission")

    def require_runtime(self, executable: dict, binding, cost) -> None:
        self.assert_unchanged()
        binding_sha, cost_sha = freeze_digest(binding, cost)
        if (digest(executable) != self._doc["executable_object_sha256"]
                or binding_sha != self._doc["evidence_binding_sha256"]
                or cost_sha != self._doc["cost_policy_sha256"]):
            raise MCFError("runtime substitutes frozen candidates/membership/cost")

    def load(self, symbol: str, timeframe: str) -> ProductionBars:
        self.assert_unchanged()
        row = self._rows.get((symbol, timeframe))
        if row is None:
            raise MCFError("symbol/timeframe outside frozen runner input")
        data = read_dataset(self.root, row)
        def field(i):
            return tuple(float(x.values[i]) for x in data)
        bars = ProductionBars(row["dataset_id"], symbol, timeframe,
                              tuple(x.open_time_ms for x in data),
                              field(1), field(2), field(3), field(4), field(5), field(7), field(8))
        bars.validate()
        return bars

    def load_timeframe(self, timeframe: str) -> dict[str, ProductionBars]:
        if timeframe not in TIMEFRAMES:
            raise MCFError("timeframe outside frozen runner input")
        return {s: self.load(s, timeframe) for s in self._doc["membership"]["selected_union_symbols"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "verify"))
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--index-relative")
    parser.add_argument("--expected-index-sha256")
    parser.add_argument("--input-relative")
    parser.add_argument("--expected-input-sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "freeze":
            if not all((args.evidence_root, args.index_relative, args.expected_index_sha256)):
                raise MCFError("freeze requires bound evidence and index")
            result = freeze_input(evidence_root=args.evidence_root, runtime_root=args.runtime_root,
                                  index_relative=args.index_relative,
                                  expected_index_sha256=args.expected_index_sha256)
        else:
            if not args.input_relative or not args.expected_input_sha256:
                raise MCFError("verify requires pinned runner input")
            reader = FrozenRunnerInput(args.runtime_root, args.input_relative, args.expected_input_sha256)
            reconcile_datasets(reader.root, reader._doc["runtime_index"])
            from .production_runtime import ProductionRuntime
            ProductionRuntime.from_frozen_input(reader)  # wiring only; run() never called
            result = {"status": "RUNNER_INPUT_VERIFIED_NO_PERFORMANCE",
                      "runner_input_sha256": args.expected_input_sha256,
                      "dataset_count": reader._doc["runtime_index"]["dataset_count"], "safety": SAFETY}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "RUNNER_INPUT_BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    # `python -m` executes this file as `__main__`; delegate to the canonical
    # package module so FrozenRunnerInput keeps one nominal class identity.
    from . import production_runner_input as _canonical_module
    raise SystemExit(_canonical_module.main())
