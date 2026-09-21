"""Mocked P10-006 integration acceptance; never real forward evidence."""

import json
import tempfile

from .economics import calculate_forward_economics
from .paper_runner import run_forward_paper
from .paper_runner_runtime import build_mock_forward_runner_fixture


def main():
    with tempfile.TemporaryDirectory() as directory:
        store, snapshot, _ = build_mock_forward_runner_fixture(directory)
        try:
            run = run_forward_paper(store, snapshot)
            first = calculate_forward_economics(store, snapshot, run)
            second = calculate_forward_economics(store, snapshot, run)
        finally:
            store.close()
    if first.canonical_json != second.canonical_json:
        raise RuntimeError("P10-006 economics replay diverged")
    record = first.as_record()
    if (record["pooled"]["completed_trades"] != 2
            or record["sample_status"] != "INSUFFICIENT_DATA"
            or record["safety"]["economic_verdict"] != "NOT_EVALUATED"):
        raise RuntimeError("P10-006 mocked economics boundary failed")
    print(json.dumps({
        "economics_id": record["economics_id"],
        "report_sha256": first.report_sha256,
        "input_run_sha256": record["input_run_sha256"],
        "pooled": record["pooled"],
        "sample_status": record["sample_status"],
        "insufficiency_reasons": record["insufficiency_reasons"],
        "replay_equal": True,
        "mocked_market_data": True,
        "real_forward_data_loaded": False,
        "real_network_called": False,
        **record["safety"],
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
