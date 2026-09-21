"""Mocked P10-007 integration acceptance; never real forward evidence."""

import json
import tempfile

from .economics import calculate_forward_economics
from .gate import GateDisposition, evaluate_forward_gate
from .paper_runner import run_forward_paper
from .paper_runner_runtime import build_mock_forward_runner_fixture


def main():
    with tempfile.TemporaryDirectory() as directory:
        store, snapshot, _ = build_mock_forward_runner_fixture(directory)
        try:
            run = run_forward_paper(store, snapshot)
            economics = calculate_forward_economics(store, snapshot, run)
            first = evaluate_forward_gate(store, snapshot, run, economics)
            second = evaluate_forward_gate(store, snapshot, run, economics)
        finally:
            store.close()

    if first.canonical_json != second.canonical_json:
        raise RuntimeError("P10-007 gate replay diverged")
    record = first.as_record()
    if record["disposition"] != GateDisposition.INSUFFICIENT_DATA.value:
        raise RuntimeError("Mocked short P10-007 evidence must remain insufficient")
    if len(record["criteria"]) != 7:
        raise RuntimeError("P10-007 did not evaluate all registered criteria")
    if record["safety"]["p11_unlocked"] is not False:
        raise RuntimeError("P10-007 must not unlock P11")

    print(json.dumps({
        "gate_id": record["gate_id"],
        "report_sha256": first.report_sha256,
        "input_economics_sha256": record["input_economics_sha256"],
        "disposition": record["disposition"],
        "criteria": {
            item["criterion"]: item["status"] for item in record["criteria"]
        },
        "replay_equal": True,
        "mocked_market_data": True,
        "real_forward_data_loaded": False,
        "real_network_called": False,
        "paper_only": record["safety"]["paper_only"],
        "live_master_lock": record["safety"]["live_master_lock"],
        "strategy_evidence": record["safety"]["strategy_evidence"],
        "p11_unlocked": record["safety"]["p11_unlocked"],
        "trade_permission": record["safety"]["trade_permission"],
        "order_endpoint": record["safety"]["order_endpoint"],
        "ai_direct_execution": record["safety"]["ai_direct_execution"],
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
