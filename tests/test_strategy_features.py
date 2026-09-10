import contextlib
import io
import unittest
from dataclasses import replace
from decimal import Decimal, localcontext
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.strategy import (FeatureError, FeatureState, atr, ema, rolling_high,
                           rolling_low, rsi, simple_return, sma)


BASE = 1_699_977_600_000


def series(closes, *, interval="1h", future=0):
    duration = INTERVAL_MILLISECONDS[interval]
    values = []
    for index, close in enumerate(closes):
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            value = Decimal(str(close))
            high = value + 1
            low = value - 1
        opened = BASE + index * duration
        values.append(Candle(
            DATA_SOURCE, "BTCUSDT", interval, opened, opened + duration - 1,
            format(value, "f"), format(high, "f"), format(low, "f"),
            format(value, "f"), "0", "0", 0, True,
        ))
    decision = BASE + (len(closes) - future) * duration
    return tuple(values), decision


class StrategyFeatureTests(unittest.TestCase):
    def test_hand_computed_return_rolling_and_average_vectors(self):
        values, decision = series((10, 11, 12, 13))
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            expected_return = Decimal(13) / Decimal(11) - 1
        self.assertEqual(simple_return(values, 2, decision).value, expected_return)
        self.assertEqual(rolling_high(values, 3, decision).value, Decimal(14))
        self.assertEqual(rolling_low(values, 3, decision).value, Decimal(10))
        self.assertEqual(sma(values, 3, decision).value, Decimal(12))
        self.assertEqual(ema(values, 3, decision).value, Decimal(12))

    def test_wilder_atr_hand_vector(self):
        values, decision = series((10, 11, 12, 13))
        result = atr(values, 3, decision)
        self.assertTrue(result.available)
        self.assertEqual(result.value, Decimal(2))
        self.assertEqual(result.warmup_required, 4)

    def test_wilder_rsi_rising_falling_and_flat(self):
        rising, decision = series((10, 11, 12, 13))
        falling, _ = series((13, 12, 11, 10))
        flat, _ = series((10, 10, 10, 10))
        self.assertEqual(rsi(rising, 3, decision).value, Decimal(100))
        self.assertEqual(rsi(falling, 3, decision).value, Decimal(0))
        self.assertEqual(rsi(flat, 3, decision).value, Decimal(50))

    def test_insufficient_history_is_explicit(self):
        values, decision = series((10, 11))
        for function in (simple_return, atr, rsi):
            result = function(values, 3, decision)
            self.assertFalse(result.available)
            self.assertEqual(result.state, FeatureState.INSUFFICIENT_HISTORY)
            self.assertIsNone(result.value)
            self.assertEqual((result.observed, result.warmup_required), (2, 4))

    def test_future_append_cannot_change_earlier_feature(self):
        prefix, decision = series((10, 11, 12, 13))
        extended, same_decision = series((10, 11, 12, 13, 99), future=1)
        altered_future = extended[:-1] + (replace(extended[-1], symbol="ETHUSDT",
                                                 is_closed=False),)
        self.assertEqual(decision, same_decision)
        functions = (simple_return, rolling_high, rolling_low, sma, ema, atr, rsi)
        for function in functions:
            with self.subTest(function=function.__name__):
                self.assertEqual(function(prefix, 3, decision),
                                 function(extended, 3, decision))
                self.assertEqual(function(prefix, 3, decision),
                                 function(altered_future, 3, decision))

    def test_gap_open_and_mixed_identity_fail_closed(self):
        values, decision = series((10, 11, 12, 13))
        invalid = (values[:1] + values[2:],
                   values[:-1] + (replace(values[-1], is_closed=False),),
                   values[:-1] + (replace(values[-1], symbol="ETHUSDT"),))
        for candles in invalid:
            with self.subTest(), self.assertRaises(FeatureError):
                sma(candles, 3, decision)

    def test_zero_volume_and_extreme_decimal_precision_are_supported(self):
        large = Decimal("9999999999999999999999999999999999999998")
        values, decision = series((large, large, large))
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            self.assertEqual(sma(values, 3, decision).value, large)
        ordinary, ordinary_decision = series((10, 11, 12))
        self.assertEqual(sma(ordinary, 3, ordinary_decision).value, Decimal(11))

    def test_invalid_inputs_and_result_tampering_fail_closed(self):
        values, decision = series((10, 11, 12))
        for period in (0, -1, 1.0, 10_001):
            with self.subTest(period=period), self.assertRaises(FeatureError):
                sma(values, period, decision)
        with self.assertRaises(FeatureError):
            sma(list(values), 2, decision)
        with self.assertRaises(FeatureError):
            sma(values, 2, 0)
        unavailable = sma(values, 4, decision)
        with self.assertRaises(FeatureError):
            replace(unavailable, state=FeatureState.READY)
        ready = sma(values, 2, decision)
        with self.assertRaises(FeatureError):
            replace(ready, value=1.0)

    @patch("sys.argv", ["yatl", "strategy-feature-check"])
    def test_cli_reports_closed_decimal_features(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("point-in-time Decimal features", text)
        self.assertIn("SMA=12", text)
        self.assertIn("ATR=2", text)
        self.assertIn("RSI=100", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
