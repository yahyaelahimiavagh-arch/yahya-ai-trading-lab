import contextlib
import io
import unittest
from dataclasses import replace
from unittest.mock import patch

from yatl.__main__ import main
from yatl.data import Candle, DATA_SOURCE
from yatl.data.history import MAX_RANGE_CANDLES
from yatl.data.quality import (
    MAX_REPAIR_RANGES,
    QualityError,
    analyze_open_times,
    duplicate_candle_keys,
)


HOUR = 3_600_000
START = 1_710_028_800_000  # 2024-03-10T08:00:00Z, independent of local DST.


def candle(open_time=START, *, symbol="BTCUSDT", closed=True):
    return Candle(
        source=DATA_SOURCE, symbol=symbol, interval="1h",
        open_time_ms=open_time, close_time_ms=open_time + HOUR - 1,
        open="60000.0", high="61000.0", low="59000.0", close="60500.0",
        base_volume="10.0", quote_volume="600000.0", trade_count=100,
        is_closed=closed,
    )


class QualityTests(unittest.TestCase):
    def test_healthy_closed_range_has_no_repairs(self):
        times = [START + index * HOUR for index in range(4)]
        report = analyze_open_times(DATA_SOURCE, "BTCUSDT", "1h", START,
                                    START + 4 * HOUR, times, START + 5 * HOUR)
        self.assertTrue(report.healthy)
        self.assertEqual(report.expected_rows, 4)
        self.assertEqual(report.observed_unique_rows, 4)
        self.assertEqual(report.repair_ranges, ())
        self.assertIsNone(report.expected_current_open_time_ms)

    def test_duplicates_and_contiguous_historical_gaps_are_reported(self):
        times = [START, START + HOUR, START + HOUR, START + 4 * HOUR]
        report = analyze_open_times(DATA_SOURCE, "BTCUSDT", "1h", START,
                                    START + 5 * HOUR, times, START + 6 * HOUR)
        self.assertFalse(report.healthy)
        self.assertEqual(report.duplicate_open_times, (START + HOUR,))
        self.assertEqual(report.historical_gap_open_times,
                         (START + 2 * HOUR, START + 3 * HOUR))
        self.assertEqual(report.repair_ranges,
                         ((START + 2 * HOUR, START + 4 * HOUR),))

    def test_missing_current_open_is_not_a_historical_gap(self):
        current = START + 4 * HOUR
        report = analyze_open_times(
            DATA_SOURCE, "ETHUSDT", "1h", START, current + HOUR,
            [START, START + HOUR, START + 2 * HOUR, START + 3 * HOUR],
            current + 123,
        )
        self.assertTrue(report.healthy)
        self.assertEqual(report.expected_current_open_time_ms, current)
        self.assertTrue(report.expected_current_open_missing)
        self.assertEqual(report.historical_gap_open_times, ())
        self.assertEqual(report.repair_ranges, ())

    def test_present_current_open_is_recognized(self):
        current = START + 2 * HOUR
        report = analyze_open_times(DATA_SOURCE, "BTCUSDT", "1h", START,
                                    current + HOUR,
                                    [START, START + HOUR, current], current + 1)
        self.assertFalse(report.expected_current_open_missing)
        self.assertTrue(report.healthy)

    def test_duplicate_canonical_keys_are_detected_before_storage(self):
        first = candle()
        same_key_update = replace(first, close="60600.0")
        other = candle(symbol="ETHUSDT")
        self.assertEqual(duplicate_candle_keys([first, other, same_key_update, first]),
                         (first.key,))
        self.assertEqual(duplicate_candle_keys([]), ())
        with self.assertRaises(QualityError):
            duplicate_candle_keys([first, object()])

    def test_exact_utc_grid_is_dst_independent_for_all_intervals(self):
        cases = (("15m", 900_000), ("1h", HOUR), ("4h", 4 * HOUR))
        for interval, duration in cases:
            aligned_start = (START // duration) * duration
            times = [aligned_start + index * duration for index in range(3)]
            with self.subTest(interval=interval):
                report = analyze_open_times(
                    DATA_SOURCE, "BTCUSDT", interval, aligned_start,
                    aligned_start + 3 * duration, times, aligned_start + 4 * duration,
                )
                self.assertTrue(report.healthy)

    def test_invalid_inputs_fail_closed(self):
        valid = (DATA_SOURCE, "BTCUSDT", "1h", START, START + HOUR, [START],
                 START + 2 * HOUR)
        cases = [
            ("OTHER", *valid[1:]),
            (valid[0], "XRPUSDT", *valid[2:]),
            (valid[0], valid[1], "5m", *valid[3:]),
            (*valid[:3], START + 1, *valid[4:]),
            (*valid[:4], START, *valid[5:]),
            (*valid[:5], [START + 1], valid[6]),
            (*valid[:5], "timestamps", valid[6]),
            (*valid[:6], True),
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(QualityError):
                analyze_open_times(*args)

    def test_future_and_oversized_ranges_are_rejected(self):
        with self.assertRaisesRegex(QualityError, "beyond"):
            analyze_open_times(DATA_SOURCE, "BTCUSDT", "1h", START,
                               START + 4 * HOUR, [], START + HOUR)
        with self.assertRaisesRegex(QualityError, "limit"):
            analyze_open_times(DATA_SOURCE, "BTCUSDT", "1h", START,
                               START + (MAX_RANGE_CANDLES + 1) * HOUR, [],
                               START + (MAX_RANGE_CANDLES + 2) * HOUR)

    def test_repair_range_count_is_bounded(self):
        end = START + (2 * MAX_REPAIR_RANGES + 2) * HOUR
        present = [START + index * HOUR
                   for index in range(0, 2 * MAX_REPAIR_RANGES + 2, 2)]
        with self.assertRaisesRegex(QualityError, "too many"):
            analyze_open_times(DATA_SOURCE, "BTCUSDT", "1h", START, end,
                               present, end + HOUR)

    @patch("sys.argv", ["yatl", "quality-check"])
    def test_runtime_cli_is_local_and_bounded(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("historical gap and expected open interval", text)
        self.assertIn("BOUNDED REPAIR RANGES ONLY", text)
        self.assertIn("No network", text)
        self.assertIn("No execution", text)


if __name__ == "__main__":
    unittest.main()
