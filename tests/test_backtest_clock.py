import contextlib
import io
import unittest
from dataclasses import replace
from unittest.mock import MagicMock, patch

from yatl.__main__ import main
from yatl.backtest import (AcceptedBacktestDataset, BacktestClock,
                           BacktestClockError, BacktestSpec, DecisionEvent)
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS


START = 1_699_977_600_000
DECISION_START = START + 8 * 3_600_000
END = DECISION_START + 4 * 3_600_000


def history(interval):
    duration = INTERVAL_MILLISECONDS[interval]
    values = []
    for opened in range(START, END, duration):
        values.append(Candle(
            DATA_SOURCE, "BTCUSDT", interval, opened, opened + duration - 1,
            "100", "110", "90", "105", "10", "1000", 20, True,
        ))
    return tuple(values)


def dataset(**changes):
    values = {
        "spec": BacktestSpec("BTCUSDT", DECISION_START, END),
        "manifest_generated_at_ms": END + 1,
        "primary": history("1h"), "context": history("15m"),
        "regime": history("4h"),
    }
    values.update(changes)
    return AcceptedBacktestDataset(**values)


class BacktestClockTests(unittest.TestCase):
    def test_exact_half_open_sequence_and_next_open_eligibility(self):
        clock = BacktestClock(dataset())
        events = tuple(clock.events())
        self.assertEqual(clock.event_count, 4)
        self.assertEqual(tuple(item.sequence for item in events), (0, 1, 2, 3))
        self.assertEqual(tuple(item.decision_time_ms for item in events),
                         tuple(range(DECISION_START, END, 3_600_000)))
        self.assertTrue(all(item.eligible_fill_open_time_ms == item.decision_time_ms
                            for item in events))

    def test_every_snapshot_excludes_current_and_future_candles(self):
        for event in BacktestClock(dataset()).events():
            for values in (event.snapshot.primary, event.snapshot.context,
                           event.snapshot.regime):
                self.assertTrue(values)
                self.assertTrue(all(item.close_time_ms < event.decision_time_ms
                                    for item in values))

    def test_identical_input_replays_byte_for_byte_equivalent_events(self):
        clock = BacktestClock(dataset())
        first = tuple(clock.events())
        second = tuple(clock.events())
        self.assertEqual(first, second)

    def test_clock_is_lazy_and_stops_when_snapshot_gate_fails(self):
        broken = dataset(primary=history("1h")[:-5])
        iterator = BacktestClock(broken).events()
        with self.assertRaises(BacktestClockError):
            next(iterator)

    def test_invalid_clock_and_event_fields_fail_closed(self):
        with self.assertRaises(BacktestClockError):
            BacktestClock(object())
        view = next(BacktestClock(dataset()).events()).snapshot
        valid = DecisionEvent(0, DECISION_START, DECISION_START, view)
        for changes in ({"sequence": -1}, {"decision_time_ms": DECISION_START + 1},
                        {"eligible_fill_open_time_ms": DECISION_START + 3_600_000},
                        {"snapshot": MagicMock()}):
            with self.subTest(changes=changes), self.assertRaises(BacktestClockError):
                replace(valid, **changes)

    @patch("yatl.__main__.load_accepted_dataset")
    @patch("yatl.__main__.latest_spec_from_manifest")
    @patch("sys.argv", ["yatl", "backtest-clock-check"])
    def test_cli_reports_safe_deterministic_replay(self, latest, load):
        data = dataset()
        latest.return_value = data.spec
        load.return_value = data
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("deterministic event clock", text)
        self.assertIn("events=4", text)
        self.assertIn("replay_equal=true", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
