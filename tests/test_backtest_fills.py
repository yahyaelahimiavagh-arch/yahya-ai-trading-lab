import contextlib
import io
import unittest
from dataclasses import replace
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import (BacktestClockError, DecisionEvent, FillModelError,
                           FillReason, IntentAction, MarketSnapshot,
                           PaperFillEngine, PaperIntent)
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS


DECISION = 1_699_999_200_000


def candle(interval, opened, *, low="99", high="106", price="100",
           volume="10", closed=True):
    duration = INTERVAL_MILLISECONDS[interval]
    return Candle(DATA_SOURCE, "BTCUSDT", interval, opened, opened + duration - 1,
                  price, high, low, price, volume, "1000", 20, closed)


def latest_history(interval, decision):
    duration = INTERVAL_MILLISECONDS[interval]
    opened = (decision // duration) * duration - duration
    return (candle(interval, opened),)


def event(decision=DECISION, sequence=0):
    view = MarketSnapshot("BTCUSDT", decision, latest_history("1h", decision),
                          latest_history("15m", decision), latest_history("4h", decision))
    return DecisionEvent(sequence, decision, decision, view)


def fill_bar(decision=DECISION, **changes):
    return candle("1h", decision, **changes)


def enter(decision=DECISION, quantity="1", stop="95", target="110"):
    return PaperIntent(IntentAction.ENTER_LONG, decision, quantity, stop, target)


class PaperIntentTests(unittest.TestCase):
    def test_action_specific_fields_and_decimal_contract(self):
        self.assertEqual(PaperIntent(IntentAction.HOLD, DECISION).action, IntentAction.HOLD)
        self.assertEqual(enter().quantity, "1")
        invalid = (
            lambda: PaperIntent("HOLD", DECISION),
            lambda: PaperIntent(IntentAction.HOLD, DECISION, "1"),
            lambda: PaperIntent(IntentAction.EXIT_LONG, DECISION, stop_price="95"),
            lambda: enter(quantity="0"), lambda: enter(quantity="1e2"),
            lambda: enter(stop="110", target="110"),
            lambda: enter(decision=DECISION + 1),
        )
        for case in invalid:
            with self.subTest(case=case), self.assertRaises(FillModelError):
                case()


class PaperFillEngineTests(unittest.TestCase):
    def test_enter_then_scripted_exit_at_consecutive_next_opens(self):
        engine = PaperFillEngine("BTCUSDT")
        first = engine.process(event(), enter(), fill_bar())
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].reason, FillReason.NEXT_PRIMARY_OPEN)
        self.assertTrue(engine.has_position)

        next_time = DECISION + 3_600_000
        second = engine.process(event(next_time, 1),
                                PaperIntent(IntentAction.EXIT_LONG, next_time),
                                fill_bar(next_time, price="102", low="101", high="103"))
        self.assertEqual((second[0].reference_price, second[0].reason),
                         ("102", FillReason.SCRIPTED_EXIT))
        self.assertFalse(engine.has_position)

    def test_hold_applies_stop_target_and_ambiguous_stop_priority(self):
        cases = (
            ({"low": "94", "high": "106"}, "95", FillReason.STOP),
            ({"low": "99", "high": "111"}, "110", FillReason.TARGET),
            ({"low": "94", "high": "111"}, "95", FillReason.AMBIGUOUS_STOP_PRIORITY),
        )
        for bar_changes, price, reason in cases:
            with self.subTest(reason=reason):
                engine = PaperFillEngine("BTCUSDT")
                engine.process(event(), enter(), fill_bar())
                next_time = DECISION + 3_600_000
                fills = engine.process(event(next_time, 1),
                                       PaperIntent(IntentAction.HOLD, next_time),
                                       fill_bar(next_time, **bar_changes))
                self.assertEqual((fills[0].reference_price, fills[0].reason),
                                 (price, reason))
                self.assertFalse(engine.has_position)

    def test_known_open_gap_precedes_ambiguous_intrabar_rule(self):
        engine = PaperFillEngine("BTCUSDT")
        engine.process(event(), enter(), fill_bar())
        next_time = DECISION + 3_600_000
        fills = engine.process(event(next_time, 1), PaperIntent(IntentAction.HOLD, next_time),
                               fill_bar(next_time, price="112", low="90", high="115"))
        self.assertEqual((fills[0].reference_price, fills[0].reason),
                         ("110", FillReason.TARGET))

    def test_entry_can_stop_conservatively_in_its_fill_candle(self):
        engine = PaperFillEngine("BTCUSDT")
        fills = engine.process(event(), enter(), fill_bar(low="94", high="111"))
        self.assertEqual(tuple(item.reason for item in fills),
                         (FillReason.NEXT_PRIMARY_OPEN,
                          FillReason.AMBIGUOUS_STOP_PRIORITY))
        self.assertFalse(engine.has_position)

    def test_overlap_exit_without_position_and_bracket_gap_fail_closed(self):
        engine = PaperFillEngine("BTCUSDT")
        with self.assertRaises(FillModelError):
            engine.process(event(), PaperIntent(IntentAction.EXIT_LONG, DECISION), fill_bar())
        engine.process(event(), enter(), fill_bar())
        with self.assertRaises(FillModelError):
            engine.process(event(), enter(), fill_bar())
        self.assertTrue(engine.has_position)

        other = PaperFillEngine("BTCUSDT")
        with self.assertRaises(FillModelError):
            other.process(event(), enter(stop="101"), fill_bar())
        self.assertFalse(other.has_position)

    def test_invalid_fill_bar_and_volume_failure_restore_state(self):
        engine = PaperFillEngine("BTCUSDT")
        for bar in (fill_bar(DECISION + 3_600_000), fill_bar(closed=False)):
            with self.subTest(bar=bar), self.assertRaises(FillModelError):
                engine.process(event(), enter(), bar)
        with self.assertRaises(FillModelError):
            engine.process(event(), enter(quantity="6"),
                           fill_bar(low="94", high="111", volume="10"))
        self.assertFalse(engine.has_position)

    def test_invalid_symbol_and_event_contract_fail_closed(self):
        with self.assertRaises(FillModelError):
            PaperFillEngine("BNBUSDT")
        with self.assertRaises(FillModelError):
            PaperFillEngine("BTCUSDT").process(object(), enter(), fill_bar())
        with self.assertRaises(FillModelError):
            PaperFillEngine("ETHUSDT").process(
                event(), enter(), replace(fill_bar(), symbol="ETHUSDT"))
        with self.assertRaises(BacktestClockError):
            replace(event(), eligible_fill_open_time_ms=DECISION + 3_600_000)
        entry_fill = PaperFillEngine("BTCUSDT").process(event(), enter(), fill_bar())[0]
        with self.assertRaises(FillModelError):
            replace(entry_fill, reason=FillReason.STOP)

    @patch("sys.argv", ["yatl", "backtest-fill-check"])
    def test_cli_reports_conservative_local_lifecycle(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("paper fill-reference lifecycle", text)
        self.assertIn("AMBIGUOUS_STOP_PRIORITY", text)
        self.assertIn("costs_pending=P2-005", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
