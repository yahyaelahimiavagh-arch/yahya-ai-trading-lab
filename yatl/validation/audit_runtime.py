"""Mocked acceptance runtime for the independent P10-010 final audit."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from .audit import audit_p10
from .cli import _pipeline, snapshot_json
from .forward_store import ForwardCandleStore
from .paper_runner_runtime import build_mock_forward_runner_fixture
from .scenarios import (
    accepted_validation_fixture,
    run_adversarial_validation_matrix,
    write_adversarial_validation_matrix,
)


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Independent P10 final economic acceptance audit"
    )
    parser.add_argument("--evidence")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store, snapshot, client = build_mock_forward_runner_fixture(root)
        database = root / "p10-forward.sqlite3"
        store.close()

        snapshot_path = root / "snapshot.json"
        snapshot_path.write_text(snapshot_json(snapshot), encoding="utf-8")

        bundle = _pipeline(database, snapshot_path)
        fixture = accepted_validation_fixture(bundle)
        matrix = run_adversarial_validation_matrix(fixture)

        if args.evidence:
            evidence = Path(args.evidence)
        else:
            evidence = root / "p10-009-evidence"
            write_adversarial_validation_matrix(matrix, evidence)

        database_sha = _sha256_file(database)
        evidence_before = {
            path.name: path.read_bytes()
            for path in sorted(evidence.iterdir(), key=lambda item: item.name)
        }

        with ForwardCandleStore(database) as accepted_store:
            result = audit_p10(
                accepted_store,
                snapshot,
                database_sha,
                evidence,
            )

        evidence_after = {
            path.name: path.read_bytes()
            for path in sorted(evidence.iterdir(), key=lambda item: item.name)
        }
        if evidence_before != evidence_after:
            raise RuntimeError("P10-010 mutated P10-009 evidence")
        if result.disposition != "INSUFFICIENT_DATA":
            raise RuntimeError("Mocked P10-010 must remain insufficient")
        if result.p11_unlocked or result.live_authorized:
            raise RuntimeError("P10-010 must not create Live authorization")

        output = {
            "schema_version": 1,
            "disposition": result.disposition,
            "database_snapshot_sha256": result.database_snapshot_sha256,
            "candidate_sha256": result.candidate_sha256,
            "gate_registry_sha256": result.gate_registry_sha256,
            "window_sha256": result.window_sha256,
            "ingestion_snapshot_sha256": result.ingestion_snapshot_sha256,
            "store_content_sha256": result.store_content_sha256,
            "paper_run_sha256": result.paper_run_sha256,
            "economics_sha256": result.economics_sha256,
            "gate_sha256": result.gate_sha256,
            "audit_sha256": result.audit_sha256,
            "adversarial_matrix_sha256": result.adversarial_matrix_sha256,
            "criteria": result.criteria,
            "scenarios": result.scenarios,
            "evidence_files": result.evidence_files,
            "exact_outcomes": result.exact_outcomes,
            "replay_equal": result.replay_equal,
            "chain_recomputed": result.chain_recomputed,
            "data_quality_recomputed": result.data_quality_recomputed,
            "adversarial_recomputed": result.adversarial_recomputed,
            "evidence_verified": result.evidence_verified,
            "candidate_unchanged": result.candidate_unchanged,
            "thresholds_unchanged": result.thresholds_unchanged,
            "no_write": result.no_write,
            "source_safe": result.source_safe,
            "continue_forward_observation": result.continue_forward_observation,
            "research_restart_required": result.research_restart_required,
            "economic_candidate_accepted": result.economic_candidate_accepted,
            "p11_consideration_allowed": result.p11_consideration_allowed,
            "p11_unlocked": result.p11_unlocked,
            "live_authorized": result.live_authorized,
            "strategy_evidence": result.strategy_evidence,
            "paper_only": True,
            "live_master_lock": "OFF",
            "real_network_called": False,
            "real_forward_data_loaded": False,
            "mocked_market_data": True,
            "server_time_calls": client.server_time_calls,
            "kline_calls": client.kline_calls,
        }
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
