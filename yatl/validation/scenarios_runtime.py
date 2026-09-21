"""Mocked P10-009 runtime over the accepted two-symbol forward-validation chain."""

import argparse
import json
import tempfile
from pathlib import Path

from .cli import _pipeline, snapshot_json
from .paper_runner_runtime import build_mock_forward_runner_fixture
from .scenarios import (
    accepted_validation_fixture,
    run_adversarial_validation_matrix,
    validation_matrix_sha256,
    write_adversarial_validation_matrix,
)


def build_mock_validation_scenario_fixture():
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    store, snapshot, client = build_mock_forward_runner_fixture(root)
    database = root / "p10-forward.sqlite3"
    store.close()
    snapshot_path = root / "snapshot.json"
    snapshot_path.write_text(snapshot_json(snapshot), encoding="utf-8")
    bundle = _pipeline(database, snapshot_path)
    return temporary, accepted_validation_fixture(bundle), client


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    temporary, fixture, client = build_mock_validation_scenario_fixture()
    try:
        matrix = run_adversarial_validation_matrix(fixture)
        if args.output:
            target = Path(args.output)
            if not target.parent.exists():
                target.parent.mkdir(parents=True)
            write_adversarial_validation_matrix(matrix, target)

        replay = run_adversarial_validation_matrix(fixture)
        if matrix != replay:
            raise RuntimeError("P10-009 adversarial matrix replay diverged")

        index = json.loads(matrix.index_json)
        output = {
            "matrix_sha256": validation_matrix_sha256(matrix),
            "scenario_count": len(matrix.runs),
            "symbols": index["symbols"],
            "all_passed": all(item["passed"] for item in index["runs"]),
            "replay_equal": True,
            "accepted_identity": index["accepted_identity"],
            "paper_only": index["paper_only"],
            "live_master_lock": index["live_master_lock"],
            "strategy_evidence": index["strategy_evidence"],
            "p11_unlocked": index["p11_unlocked"],
            "trade_permission": index["trade_permission"],
            "order_endpoint": index["order_endpoint"],
            "ai_direct_execution": index["ai_direct_execution"],
            "real_network_called": False,
            "real_forward_data_loaded": False,
            "mocked_market_data": True,
            "server_time_calls": client.server_time_calls,
            "kline_calls": client.kline_calls,
        }
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    finally:
        temporary.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
