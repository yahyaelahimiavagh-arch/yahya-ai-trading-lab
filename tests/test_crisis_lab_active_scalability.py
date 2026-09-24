import inspect
import unittest

from research.crisis_lab import active_diagnostic as diagnostic
from research.crisis_lab import controls
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS


START_MS = 1_704_067_200_000
DAY_MS = 86_400_000
POOL_START_MS = START_MS + 10 * DAY_MS
POOL_END_MS = START_MS + 45 * DAY_MS
PRIMARY_MS = INTERVAL_MILLISECONDS["1h"]


def candles(symbol, interval):
    duration = INTERVAL_MILLISECONDS[interval]
    values = []
    for index, open_ms in enumerate(
        range(START_MS, POOL_END_MS, duration)
    ):
        if interval == "4h":
            step = 100
            price = 10_000 + index * step
            low = price - 20
            high = price + 20
            close = price + 10
        elif interval == "1h":
            step = 10
            price = 10_000 + index * step
            # A pullback is visible at the decision one hour later.
            pullback = index in {239, 407, 575, 743, 911}
            low = price - (120 if pullback else 3)
            high = price + 4
            close = price + 2
        else:
            step = 1
            price = 10_000 + index * step
            low = price - 1
            high = price + 2
            close = price + 1

        values.append(
            Candle(
                source=DATA_SOURCE,
                symbol=symbol,
                interval=interval,
                open_time_ms=open_ms,
                close_time_ms=open_ms + duration - 1,
                open=str(price),
                high=str(high),
                low=str(low),
                close=str(close),
                base_volume="100",
                quote_volume="1000000",
                trade_count=100,
                is_closed=True,
            )
        )
    return tuple(values)


def corpus():
    datasets = {}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        for interval in ("15m", "1h", "4h"):
            datasets[(symbol, interval)] = candles(symbol, interval)
    return controls.AdmittedControlCorpus(
        event_id=controls.CONTROL_CORPUS_ID,
        designation="DEVELOPMENT",
        quality_manifest_relative_path=(
            "quality/event-quality-" + "a" * 24 + ".json"
        ),
        quality_manifest_file_sha256="a" * 64,
        event_acquisition_manifest_relative_path=(
            "manifests/event-acquisition-" + "b" * 24 + ".json"
        ),
        event_acquisition_manifest_sha256="b" * 64,
        retrieved_at_ms=POOL_END_MS + DAY_MS,
        datasets=datasets,
    )


class CrisisLabStrategyActiveScalabilityTests(unittest.TestCase):
    def _run(self, chunk_days):
        event = diagnostic._pool_event(
            corpus=corpus(),
            protocol_sha256="c" * 64,
            pool_start_ms=POOL_START_MS,
            pool_end_ms=POOL_END_MS,
        )
        return diagnostic._scan_progressive(
            event=event,
            exclusions=(),
            maximum_episodes=3,
            minimum_separation_ms=7 * DAY_MS,
            chunk_ms=chunk_days * DAY_MS,
        )

    def test_partition_size_does_not_change_selected_evidence(self):
        scans7, selected7, runtime7 = self._run(7)
        scans14, selected14, runtime14 = self._run(14)

        self.assertEqual(len(selected7), 3)
        self.assertEqual(selected7, selected14)
        self.assertEqual(scans7, scans14)
        self.assertEqual(
            runtime7["scanned_end_exclusive_ms"],
            runtime14["scanned_end_exclusive_ms"],
        )
        self.assertEqual(
            runtime7["stop_reason"],
            runtime14["stop_reason"],
        )
        self.assertEqual(runtime7["stop_reason"], "TARGET_REACHED")
        self.assertTrue(runtime7["stopped_early"])
        self.assertTrue(runtime14["stopped_early"])

    def test_global_tie_break_remains_btc_then_eth(self):
        _, selected, _ = self._run(14)
        # Both fixture symbols are identical, so simultaneous eligible
        # entries must resolve by the frozen lexical symbol tie-break.
        self.assertTrue(selected)
        self.assertTrue(
            all(item["symbol"] == "BTCUSDT" for item in selected)
        )

    def test_scanner_does_not_materialize_full_event_sequence(self):
        source = inspect.getsource(diagnostic)
        self.assertNotIn(
            "tuple(BacktestClock(dataset).events())",
            source,
        )
        self.assertIn("SCAN_CHUNK_MS", source)
        self.assertIn("_scan_progressive", source)

    def test_partition_is_hour_aligned_and_fail_closed(self):
        event = diagnostic._pool_event(
            corpus=corpus(),
            protocol_sha256="d" * 64,
            pool_start_ms=POOL_START_MS,
            pool_end_ms=POOL_END_MS,
        )
        with self.assertRaises(diagnostic.DiagnosticError):
            diagnostic._scan_progressive(
                event=event,
                exclusions=(),
                maximum_episodes=3,
                minimum_separation_ms=7 * DAY_MS,
                chunk_ms=PRIMARY_MS + 1,
            )


if __name__ == "__main__":
    unittest.main()
