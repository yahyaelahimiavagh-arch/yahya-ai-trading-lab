import inspect
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from yatl.data import (
    BINANCE_MARKET_DATA_BASE_URL,
    BINANCE_PUBLIC_BASE_URL,
    DATA_SOURCE,
    INTERVAL_MILLISECONDS,
    BinancePublicRestClient,
    Candle,
    CandleStore,
)

from yatl.validation.forward_store import (
    FORWARD_STORE_KIND,
    ForwardCandleStore,
    ForwardStoreError,
)
from yatl.validation.ingestion import (
    FORWARD_DATASET_KIND,
    FORWARD_INGESTION_ID,
    ForwardIngestionError,
    collect_forward_snapshot,
    snapshot_from_record,
)
from yatl.validation.window import ForwardWindowSeal


class MockPublicClient(BinancePublicRestClient):
    def __init__(self, server_time_ms, *, mode="normal",
                 base_url=BINANCE_PUBLIC_BASE_URL):
        super().__init__(base_url=base_url)
        self._server_time_ms = server_time_ms
        self.mode = mode
        self.server_time_calls = 0
        self.kline_calls = 0

    def server_time(self):
        self.server_time_calls += 1
        return self._server_time_ms

    def klines(self, symbol, interval, *, limit=1000,
               start_time=None, end_time=None):
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

        if self.mode == "gap" and len(rows) >= 3:
            del rows[1]
        elif self.mode == "duplicate" and len(rows) >= 2:
            rows.insert(1, list(rows[0]))
        elif self.mode == "malformed" and rows:
            rows[0][1] = "not-a-decimal"
        elif self.mode == "wrong_close" and rows:
            rows[0][6] += 1
        return rows


def server_time_after_eight_hours():
    return ForwardWindowSeal().forward_window_start_ms + 8 * 3_600_000 + 1_234


def canonical_candle(open_time_ms, *, is_closed=True):
    duration = INTERVAL_MILLISECONDS["1h"]
    return Candle(
        source=DATA_SOURCE,
        symbol="BTCUSDT",
        interval="1h",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + duration - 1,
        open="100",
        high="101",
        low="99",
        close="100",
        base_volume="1",
        quote_volume="100",
        trade_count=10,
        is_closed=is_closed,
    )


class ForwardStoreTests(unittest.TestCase):
    def test_store_is_window_bound_and_reopenable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forward.sqlite3"
            with ForwardCandleStore(path) as first:
                self.assertEqual(first.store_kind, FORWARD_STORE_KIND)
                self.assertEqual(first.count(), 0)
                sha = first.window_sha256
            with ForwardCandleStore(path) as second:
                self.assertEqual(second.window_sha256, sha)
                self.assertEqual(second.count(), 0)

    def test_store_refuses_nonempty_unowned_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.sqlite3"
            window = ForwardWindowSeal()
            with CandleStore(path) as store:
                store.write(canonical_candle(window.forward_window_start_ms))
            with self.assertRaises(ForwardStoreError):
                ForwardCandleStore(path)

    def test_store_refuses_corrupted_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forward.sqlite3"
            with ForwardCandleStore(path):
                pass
            connection = sqlite3.connect(path)
            with connection:
                connection.execute(
                    "UPDATE p10_forward_metadata SET window_sha256 = ?",
                    ("0" * 64,),
                )
            connection.close()
            with self.assertRaises(ForwardStoreError):
                ForwardCandleStore(path)

    def test_store_rejects_pre_window_candle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forward.sqlite3"
            window = ForwardWindowSeal()
            with ForwardCandleStore(path) as store:
                with self.assertRaises(ForwardStoreError):
                    store.write_many([
                        canonical_candle(
                            window.forward_window_start_ms
                            - INTERVAL_MILLISECONDS["1h"]
                        )
                    ])

    def test_store_rejects_open_candle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forward.sqlite3"
            window = ForwardWindowSeal()
            with ForwardCandleStore(path) as store:
                with self.assertRaises(ForwardStoreError):
                    store.write_many([
                        canonical_candle(
                            window.forward_window_start_ms,
                            is_closed=False,
                        )
                    ])

    def test_store_range_cannot_read_before_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forward.sqlite3"
            window = ForwardWindowSeal()
            with ForwardCandleStore(path) as store:
                with self.assertRaises(ForwardStoreError):
                    store.candles_between(
                        "BTCUSDT",
                        "1h",
                        window.forward_window_start_ms
                        - INTERVAL_MILLISECONDS["1h"],
                        window.forward_window_start_ms,
                    )


class ForwardIngestionTests(unittest.TestCase):
    def collect(self, *, mode="normal", server_time_ms=None,
                base_url=BINANCE_PUBLIC_BASE_URL):
        if server_time_ms is None:
            server_time_ms = server_time_after_eight_hours()
        temporary = tempfile.TemporaryDirectory()
        path = Path(temporary.name) / "forward.sqlite3"
        store = ForwardCandleStore(path)
        client = MockPublicClient(
            server_time_ms,
            mode=mode,
            base_url=base_url,
        )
        return temporary, store, client

    def test_complete_snapshot_has_exact_six_dataset_pairs(self):
        temporary, store, client = self.collect()
        try:
            snapshot = collect_forward_snapshot(store, client)
            self.assertEqual(snapshot.ingestion_id, FORWARD_INGESTION_ID)
            self.assertEqual(snapshot.dataset_kind, FORWARD_DATASET_KIND)
            self.assertEqual(
                tuple((item.symbol, item.interval) for item in snapshot.datasets),
                (
                    ("BTCUSDT", "15m"),
                    ("BTCUSDT", "1h"),
                    ("BTCUSDT", "4h"),
                    ("ETHUSDT", "15m"),
                    ("ETHUSDT", "1h"),
                    ("ETHUSDT", "4h"),
                ),
            )
        finally:
            store.close()
            temporary.cleanup()

    def test_snapshot_row_counts_match_eight_hour_cutoffs(self):
        temporary, store, client = self.collect()
        try:
            snapshot = collect_forward_snapshot(store, client)
            counts = {
                (item.symbol, item.interval): item.total_rows
                for item in snapshot.datasets
            }
            for symbol in ("BTCUSDT", "ETHUSDT"):
                self.assertEqual(counts[(symbol, "15m")], 32)
                self.assertEqual(counts[(symbol, "1h")], 8)
                self.assertEqual(counts[(symbol, "4h")], 2)
            self.assertEqual(store.count(), 84)
        finally:
            store.close()
            temporary.cleanup()

    def test_snapshot_is_bound_to_window_candidate_gates_and_source_manifest(self):
        temporary, store, client = self.collect()
        try:
            snapshot = collect_forward_snapshot(store, client)
            window = ForwardWindowSeal()
            self.assertEqual(snapshot.window_sha256, window.window_sha256)
            self.assertEqual(snapshot.candidate_sha256, window.candidate_sha256)
            self.assertEqual(
                snapshot.gate_registry_sha256,
                window.gate_registry_sha256,
            )
            self.assertEqual(
                snapshot.p10_002_registration_sha256,
                window.p10_002_registration_sha256,
            )
            self.assertEqual(
                snapshot.accepted_source_manifest_git_blob_sha1,
                window.accepted_source_manifest_git_blob_sha1,
            )
        finally:
            store.close()
            temporary.cleanup()

    def test_snapshot_is_quality_pass_and_not_economic_evidence(self):
        temporary, store, client = self.collect()
        try:
            snapshot = collect_forward_snapshot(store, client)
            self.assertTrue(snapshot.quality_pass)
            self.assertFalse(snapshot.upstream_write_allowed)
            self.assertFalse(snapshot.p1_manifest_write_allowed)
            self.assertFalse(snapshot.economic_evaluation_allowed)
            self.assertEqual(snapshot.strategy_evidence, "INSUFFICIENT_EVIDENCE")
            self.assertTrue(snapshot.paper_only)
            self.assertEqual(snapshot.live_master_lock, "OFF")
            self.assertFalse(snapshot.trade_permission)
            self.assertFalse(snapshot.order_endpoint)
            self.assertFalse(snapshot.ai_direct_execution)
        finally:
            store.close()
            temporary.cleanup()

    def test_repeated_collection_is_exactly_replay_equal(self):
        temporary, store, client = self.collect()
        try:
            first = collect_forward_snapshot(store, client)
            first_count = store.count()
            second = collect_forward_snapshot(store, client)
            self.assertEqual(first.as_record(), second.as_record())
            self.assertEqual(first.snapshot_sha256, second.snapshot_sha256)
            self.assertEqual(store.count(), first_count)
        finally:
            store.close()
            temporary.cleanup()

    def test_fresh_stores_produce_same_snapshot_identity(self):
        items = []
        for _ in range(2):
            temporary, store, client = self.collect()
            try:
                snapshot = collect_forward_snapshot(store, client)
                items.append(snapshot.snapshot_sha256)
            finally:
                store.close()
                temporary.cleanup()
        self.assertEqual(items[0], items[1])

    def test_snapshot_strict_round_trip(self):
        temporary, store, client = self.collect()
        try:
            snapshot = collect_forward_snapshot(store, client)
            restored = snapshot_from_record(snapshot.as_record())
            self.assertEqual(restored, snapshot)
            self.assertEqual(restored.snapshot_sha256, snapshot.snapshot_sha256)
        finally:
            store.close()
            temporary.cleanup()

    def test_snapshot_rejects_schema_smuggling(self):
        temporary, store, client = self.collect()
        try:
            snapshot = collect_forward_snapshot(store, client)
            record = snapshot.as_record()
            record["economic_result"] = "PASS_CANDIDATE"
            with self.assertRaises(ForwardIngestionError):
                snapshot_from_record(record)
        finally:
            store.close()
            temporary.cleanup()

    def test_before_first_closed_four_hour_candle_fails_without_kline_calls(self):
        window = ForwardWindowSeal()
        temporary, store, client = self.collect(
            server_time_ms=window.forward_window_start_ms + 3_600_000,
        )
        try:
            with self.assertRaises(ForwardIngestionError):
                collect_forward_snapshot(store, client)
            self.assertEqual(client.kline_calls, 0)
            self.assertEqual(store.count(), 0)
        finally:
            store.close()
            temporary.cleanup()

    def test_non_primary_public_host_is_rejected_before_network_use(self):
        temporary, store, client = self.collect(
            base_url=BINANCE_MARKET_DATA_BASE_URL,
        )
        try:
            with self.assertRaises(ForwardIngestionError):
                collect_forward_snapshot(store, client)
            self.assertEqual(client.server_time_calls, 0)
            self.assertEqual(client.kline_calls, 0)
        finally:
            store.close()
            temporary.cleanup()

    def test_gap_fails_quality_gate(self):
        temporary, store, client = self.collect(mode="gap")
        try:
            with self.assertRaises(ForwardIngestionError):
                collect_forward_snapshot(store, client)
        finally:
            store.close()
            temporary.cleanup()

    def test_duplicate_remote_rows_fail_closed(self):
        temporary, store, client = self.collect(mode="duplicate")
        try:
            with self.assertRaises(ForwardIngestionError):
                collect_forward_snapshot(store, client)
        finally:
            store.close()
            temporary.cleanup()

    def test_malformed_remote_row_fails_closed(self):
        temporary, store, client = self.collect(mode="malformed")
        try:
            with self.assertRaises(ForwardIngestionError):
                collect_forward_snapshot(store, client)
        finally:
            store.close()
            temporary.cleanup()

    def test_wrong_remote_close_boundary_fails_closed(self):
        temporary, store, client = self.collect(mode="wrong_close")
        try:
            with self.assertRaises(ForwardIngestionError):
                collect_forward_snapshot(store, client)
        finally:
            store.close()
            temporary.cleanup()

    def test_p1_manifest_is_byte_unchanged(self):
        before = Path("manifests/p1-market-data.json").read_bytes()
        temporary, store, client = self.collect()
        try:
            collect_forward_snapshot(store, client)
        finally:
            store.close()
            temporary.cleanup()
        self.assertEqual(
            before,
            Path("manifests/p1-market-data.json").read_bytes(),
        )

    def test_dataset_and_health_digests_are_present_and_distinct_per_interval(self):
        temporary, store, client = self.collect()
        try:
            snapshot = collect_forward_snapshot(store, client)
            for item in snapshot.datasets:
                self.assertEqual(len(item.dataset_sha256), 64)
                self.assertEqual(len(item.health_sha256), 64)
                self.assertNotEqual(item.dataset_sha256, item.health_sha256)
        finally:
            store.close()
            temporary.cleanup()

    def test_ingestion_source_has_no_execution_account_risk_or_secret_capability(self):
        import yatl.validation.ingestion as ingestion

        source = inspect.getsource(ingestion)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "from yatl.analyst",
            "import yatl.analyst",
            "from yatl.notifications",
            "import yatl.notifications",
            "os.getenv",
            "os.environ",
            "dotenv",
            "API_KEY",
            "API_SECRET",
            "openai",
            "anthropic",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
            "time.time",
            "datetime",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_forward_store_source_has_no_network_or_execution_capability(self):
        import yatl.validation.forward_store as forward_store

        source = inspect.getsource(forward_store)
        for forbidden in (
            "urllib",
            "http.client",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "openai",
            "anthropic",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
