"""Mocked operational runtime for the production P10 forward collector."""

import json
import tempfile
from pathlib import Path

from yatl.data import BINANCE_PUBLIC_BASE_URL, INTERVAL_MILLISECONDS, BinancePublicRestClient

from .collector_cli import collect_once
from .ingestion import snapshot_from_record
from .window import ForwardWindowSeal


class _MockPublicClient(BinancePublicRestClient):
    def __init__(self, server_time_ms):
        super().__init__(base_url=BINANCE_PUBLIC_BASE_URL)
        self._server_time_ms = server_time_ms
        self.server_time_calls = 0
        self.kline_calls = 0

    def server_time(self):
        self.server_time_calls += 1
        return self._server_time_ms

    def klines(self, symbol, interval, *, limit=1000, start_time=None, end_time=None):
        self.kline_calls += 1
        duration = INTERVAL_MILLISECONDS[interval]
        rows = []
        cursor = start_time
        while cursor is not None and end_time is not None and cursor <= end_time:
            rows.append([
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
            if len(rows) >= limit:
                break
        return rows


def main():
    window = ForwardWindowSeal()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        database = root / "p10-forward.sqlite3"
        snapshot_path = root / "snapshot.json"

        first_client = _MockPublicClient(
            window.forward_window_start_ms + 8 * 3_600_000 + 1_234
        )
        first = collect_once(database, snapshot_path, client=first_client)
        first_bytes = snapshot_path.read_bytes()

        second_client = _MockPublicClient(
            window.forward_window_start_ms + 12 * 3_600_000 + 1_234
        )
        second = collect_once(database, snapshot_path, client=second_client)
        second_bytes = snapshot_path.read_bytes()

        restored = snapshot_from_record(
            json.loads(second_bytes.decode("utf-8"))
        )
        if (
            first["store_count"] != 84
            or second["store_count"] != 126
            or first["snapshot_sha256"] == second["snapshot_sha256"]
            or first_bytes == second_bytes
            or restored.snapshot_sha256 != second["snapshot_sha256"]
            or second["quality_pass"] is not True
            or second["paper_only"] is not True
            or second["live_master_lock"] != "OFF"
            or second["trade_permission"] is not False
            or second["order_endpoint"] is not False
            or second["ai_direct_execution"] is not False
        ):
            raise RuntimeError("P10 operational collector runtime failed")

        output = {
            "schema_version": 1,
            "first_store_count": first["store_count"],
            "second_store_count": second["store_count"],
            "snapshot_advanced": True,
            "quality_pass": second["quality_pass"],
            "paper_only": second["paper_only"],
            "live_master_lock": second["live_master_lock"],
            "strategy_evidence": second["strategy_evidence"],
            "trade_permission": second["trade_permission"],
            "order_endpoint": second["order_endpoint"],
            "ai_direct_execution": second["ai_direct_execution"],
            "mocked_market_data": True,
            "real_network_called": False,
            "first_server_time_calls": first_client.server_time_calls,
            "first_kline_calls": first_client.kline_calls,
            "second_server_time_calls": second_client.server_time_calls,
            "second_kline_calls": second_client.kline_calls,
        }
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
