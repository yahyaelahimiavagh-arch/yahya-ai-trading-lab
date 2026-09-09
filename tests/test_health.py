import contextlib
import io
import json
import unittest
from unittest.mock import MagicMock, patch

from yatl.__main__ import main
from yatl.data import Candle, DATA_SOURCE
from yatl.data.health import HealthError, build_health_report


HOUR = 3_600_000
START = 1_699_999_200_000


def candle(open_time, *, closed=True, symbol="BTCUSDT"):
    return Candle(
        source=DATA_SOURCE, symbol=symbol, interval="1h",
        open_time_ms=open_time, close_time_ms=open_time + HOUR - 1,
        open="26000.0", high="26250.0", low="25900.0", close="26100.0",
        base_volume="123.0", quote_volume="3210000.0", trade_count=100,
        is_closed=closed,
    )


class HealthTests(unittest.TestCase):
    def test_complete_closed_range_is_backtest_ready(self):
        values = [candle(START + index * HOUR) for index in range(3)]
        report = build_health_report(DATA_SOURCE, "BTCUSDT", "1h", START,
                                     START + 3 * HOUR, values, START + 4 * HOUR)
        self.assertTrue(report.backtest_ready)
        self.assertTrue(report.fresh)
        self.assertEqual((report.total_rows, report.closed_rows, report.open_rows), (3, 3, 0))
        self.assertEqual(report.failure_reasons, ())

    def test_current_open_is_allowed_and_excluded_from_closed_count(self):
        current = START + 2 * HOUR
        values = [candle(START), candle(START + HOUR), candle(current, closed=False)]
        report = build_health_report(DATA_SOURCE, "BTCUSDT", "1h", START,
                                     current + HOUR, values, current + 10)
        self.assertTrue(report.backtest_ready)
        self.assertEqual((report.closed_rows, report.open_rows), (2, 1))
        self.assertEqual(report.unexpected_open_times, ())

    def test_missing_current_open_is_still_historically_ready(self):
        current = START + 2 * HOUR
        report = build_health_report(DATA_SOURCE, "BTCUSDT", "1h", START,
                                     current + HOUR, [candle(START), candle(START + HOUR)],
                                     current + 10)
        self.assertTrue(report.backtest_ready)
        self.assertTrue(report.expected_current_open_missing)

    def test_gaps_duplicates_and_unexpected_open_fail(self):
        values = [candle(START, closed=False), candle(START),
                  candle(START + 2 * HOUR)]
        report = build_health_report(DATA_SOURCE, "BTCUSDT", "1h", START,
                                     START + 3 * HOUR, values, START + 4 * HOUR)
        self.assertFalse(report.backtest_ready)
        self.assertEqual(report.duplicate_open_times, (START,))
        self.assertEqual(report.historical_gap_open_times, (START + HOUR,))
        self.assertEqual(report.repair_ranges, ((START + HOUR, START + 2 * HOUR),))
        self.assertEqual(report.unexpected_open_times, (START,))
        self.assertEqual(report.failure_reasons,
                         ("duplicates", "historical_gaps", "unexpected_open_candles"))

    def test_diagnostics_and_staleness_fail_closed(self):
        values = [candle(START)]
        report = build_health_report(DATA_SOURCE, "BTCUSDT", "1h", START,
                                     START + 2 * HOUR, values, START + 3 * HOUR,
                                     malformed_rows=2, conflicting_rows=1)
        self.assertFalse(report.fresh)
        self.assertEqual(report.freshness_ms, 2 * HOUR)
        self.assertEqual(report.failure_reasons,
                         ("historical_gaps", "malformed_rows", "conflicting_rows",
                          "stale_closed_data"))

    def test_json_is_deterministic_and_machine_readable(self):
        report = build_health_report(DATA_SOURCE, "BTCUSDT", "1h", START,
                                     START + HOUR, [candle(START)], START + 2 * HOUR)
        first = report.to_json()
        self.assertEqual(first, report.to_json())
        parsed = json.loads(first)
        self.assertTrue(parsed["backtest_ready"])
        self.assertEqual(parsed["requested_start_time_ms"], START)
        self.assertNotIn(" ", first)

    def test_human_output_contains_required_health_fields(self):
        report = build_health_report(DATA_SOURCE, "BTCUSDT", "1h", START,
                                     START + HOUR, [candle(START)], START + 2 * HOUR)
        text = report.to_text()
        for field in ("requested=", "stored=", "closed=", "open=", "duplicates=",
                      "gaps=", "malformed=", "conflicts=", "fresh=",
                      "backtest_ready=", "reasons="):
            self.assertIn(field, text)

    def test_invalid_identity_candles_and_diagnostics_fail_closed(self):
        valid = (DATA_SOURCE, "BTCUSDT", "1h", START, START + HOUR,
                 [candle(START)], START + 2 * HOUR)
        cases = [
            ("OTHER", *valid[1:]),
            (valid[0], "ETHUSDT", *valid[2:]),
            (*valid[:5], [candle(START, symbol="ETHUSDT")], valid[6]),
            (*valid[:3], "bad-start", *valid[4:]),
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(HealthError):
                build_health_report(*args)
        for kwargs in ({"malformed_rows": -1}, {"conflicting_rows": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(HealthError):
                build_health_report(*valid, **kwargs)

    @patch("sys.argv", ["yatl", "health-check"])
    def test_cli_human_report_passes(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertIn("PASS: BINANCE_SPOT_PUBLIC BTCUSDT 1h", output.getvalue())
        self.assertIn("No execution", output.getvalue())

    @patch("sys.argv", ["yatl", "health-check", "--json"])
    def test_cli_json_report_passes(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        first_line = output.getvalue().splitlines()[0]
        self.assertTrue(json.loads(first_line)["backtest_ready"])

    @patch("yatl.__main__.build_health_report")
    @patch("sys.argv", ["yatl", "health-check"])
    def test_cli_exits_nonzero_when_health_gate_fails(self, build):
        build.return_value = MagicMock(backtest_ready=False, to_text=lambda: "FAIL")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertIn("FAIL", output.getvalue())


if __name__ == "__main__":
    unittest.main()
