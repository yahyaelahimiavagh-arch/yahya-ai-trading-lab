"""Deterministic mocked runtime for P10-004 forward ingestion."""

import json
import tempfile
from pathlib import Path

from yatl.data import BinancePublicRestClient, INTERVAL_MILLISECONDS

from .forward_store import ForwardCandleStore
from .ingestion import collect_forward_snapshot, snapshot_from_record
from .window import ForwardWindowSeal


class _MockPublicClient(BinancePublicRestClient):
    def __init__(self, server_time_ms):
        super().__init__()
        self._server_time_ms = server_time_ms
        self.server_time_calls = 0
        self.kline_calls = 0

    def server_time(self):
        self.server_time_calls += 1
        return self._server_time_ms

    def klines(self, symbol, interval, *, limit=1000,
               start_time=None, end_time=None):
        self.kline_calls += 1
        duration = INTERVAL_MILLISECONDS[interval]
        values = []
        cursor = start_time
        while cursor is not None and end_time is not None and cursor <= end_time:
            values.append([
                cursor,
                "100",
                "101",
                "99",
                "100",
                "1",
                cursor + duration - 1,
                "100",
                10,
                "0",
                "0",
                "0",
            ])
            cursor += duration
            if len(values) >= limit:
                break
        return values


def main():
    window = ForwardWindowSeal()
    server_time = window.forward_window_start_ms + 8 * 3_600_000 + 1_234
    manifest_path = Path("manifests/p1-market-data.json")
    before = manifest_path.read_bytes()

    with tempfile.TemporaryDirectory() as directory:
        store_path = Path(directory) / "p10-forward.sqlite3"
        client = _MockPublicClient(server_time)
        with ForwardCandleStore(store_path) as store:
            first = collect_forward_snapshot(store, client)
            first_count = store.count()
            second = collect_forward_snapshot(store, client)
            second_count = store.count()

        restored = snapshot_from_record(first.as_record())
        if (
            restored != first
            or first.snapshot_sha256 != second.snapshot_sha256
            or first.as_record() != second.as_record()
            or first_count != second_count
            or before != manifest_path.read_bytes()
        ):
            raise RuntimeError("P10-004 deterministic replay or isolation failed")

    output = {
        "ingestion_id": first.ingestion_id,
        "snapshot_sha256": first.snapshot_sha256,
        "window_sha256": first.window_sha256,
        "candidate_sha256": first.candidate_sha256,
        "gate_registry_sha256": first.gate_registry_sha256,
        "generated_at_ms": first.generated_at_ms,
        "dataset_count": len(first.datasets),
        "dataset_sha256": {
            f"{item.symbol}:{item.interval}": item.dataset_sha256
            for item in first.datasets
        },
        "health_sha256": {
            f"{item.symbol}:{item.interval}": item.health_sha256
            for item in first.datasets
        },
        "quality_pass": first.quality_pass,
        "store_count": first_count,
        "replay_store_count": second_count,
        "replay_equal": first.as_record() == second.as_record(),
        "upstream_manifest_unchanged": before == manifest_path.read_bytes(),
        "p1_manifest_write_allowed": first.p1_manifest_write_allowed,
        "upstream_write_allowed": first.upstream_write_allowed,
        "economic_evaluation_allowed": first.economic_evaluation_allowed,
        "strategy_evidence": first.strategy_evidence,
        "paper_only": first.paper_only,
        "live_master_lock": first.live_master_lock,
        "trade_permission": first.trade_permission,
        "order_endpoint": first.order_endpoint,
        "ai_direct_execution": first.ai_direct_execution,
        "mocked_transport": True,
        "real_network_called": False,
        "real_forward_data_loaded": False,
        "server_time_calls": client.server_time_calls,
        "kline_calls": client.kline_calls,
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
