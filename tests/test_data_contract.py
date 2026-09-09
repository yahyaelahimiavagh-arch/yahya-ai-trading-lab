import dataclasses
import unittest

from yatl.data import (
    BINANCE_PUBLIC_BASE_URL,
    Candle,
    CandleValidationError,
    DATA_SOURCE,
    INTERVAL_MILLISECONDS,
    SYMBOLS,
    TIMEFRAME_POLICY,
)


OPEN_TIME = 1_699_999_200_000


def candle(**changes):
    values = {
        "source": DATA_SOURCE,
        "symbol": "BTCUSDT",
        "interval": "1h",
        "open_time_ms": OPEN_TIME,
        "close_time_ms": OPEN_TIME + 3_600_000 - 1,
        "open": "26000.10000000",
        "high": "26250.00000000",
        "low": "25900.00000000",
        "close": "26100.25000000",
        "base_volume": "123.45000000",
        "quote_volume": "3210000.12345678",
        "trade_count": 1234,
        "is_closed": True,
    }
    values.update(changes)
    return Candle(**values)


class DataConfigurationTests(unittest.TestCase):
    def test_policy_is_exact_and_immutable(self):
        self.assertEqual(BINANCE_PUBLIC_BASE_URL, "https://api.binance.com")
        self.assertEqual(DATA_SOURCE, "BINANCE_SPOT_PUBLIC")
        self.assertEqual(SYMBOLS, ("BTCUSDT", "ETHUSDT"))
        self.assertEqual(dict(INTERVAL_MILLISECONDS), {
            "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000,
        })
        self.assertEqual(dict(TIMEFRAME_POLICY), {
            "primary_analysis": "1h", "higher_timeframe_regime": "4h",
            "entry_context": "15m", "execution": "NOT_ENABLED",
        })
        with self.assertRaises(TypeError):
            INTERVAL_MILLISECONDS["5m"] = 300_000


class CandleContractTests(unittest.TestCase):
    def test_valid_candle_preserves_decimal_strings_and_key(self):
        value = candle()
        self.assertEqual(value.open, "26000.10000000")
        self.assertEqual(value.key, (DATA_SOURCE, "BTCUSDT", "1h", OPEN_TIME))
        self.assertEqual(value.as_record()["quote_volume"], "3210000.12345678")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            value.close = "1"

    def test_allowed_symbols_intervals_and_open_state(self):
        self.assertEqual(candle(symbol="ETHUSDT").symbol, "ETHUSDT")
        for interval, duration in INTERVAL_MILLISECONDS.items():
            aligned = (OPEN_TIME // duration) * duration
            value = candle(interval=interval, open_time_ms=aligned,
                           close_time_ms=aligned + duration - 1, is_closed=False)
            self.assertFalse(value.is_closed)

    def test_source_symbol_and_interval_fail_closed(self):
        for changes in ({"source": "BINANCE_TESTNET"}, {"symbol": "XRPUSDT"},
                        {"symbol": "btcusdt"}, {"interval": "5m"},
                        {"interval": "1d"}):
            with self.subTest(changes=changes), self.assertRaises(CandleValidationError):
                candle(**changes)

    def test_timestamp_contract_fails_closed(self):
        for changes in ({"open_time_ms": -1}, {"open_time_ms": True},
                        {"open_time_ms": OPEN_TIME + 1},
                        {"close_time_ms": OPEN_TIME + 3_600_000},
                        {"close_time_ms": "1700002799999"}):
            with self.subTest(changes=changes), self.assertRaises(CandleValidationError):
                candle(**changes)

    def test_decimal_contract_fails_closed(self):
        bad_values = (1, "", "-1", "+1", "01", ".1", "1.", "1e3", "NaN",
                      "Infinity", " 1", "1 ", "1,000")
        for field in ("open", "high", "low", "close", "base_volume", "quote_volume"):
            for bad in bad_values:
                with self.subTest(field=field, bad=bad), self.assertRaises(CandleValidationError):
                    candle(**{field: bad})
        for field in ("open", "high", "low", "close"):
            with self.subTest(field=field), self.assertRaises(CandleValidationError):
                candle(**{field: "0"})
        self.assertEqual(candle(base_volume="0", quote_volume="0").base_volume, "0")

    def test_ohlc_invariants_fail_closed(self):
        for changes in ({"low": "26100.25000001"}, {"high": "26000.00000000"},
                        {"close": "26300.00000000"}):
            with self.subTest(changes=changes), self.assertRaises(CandleValidationError):
                candle(**changes)

    def test_trade_count_and_state_types_fail_closed(self):
        for changes in ({"trade_count": -1}, {"trade_count": True},
                        {"trade_count": "1"}, {"is_closed": 1},
                        {"is_closed": "true"}):
            with self.subTest(changes=changes), self.assertRaises(CandleValidationError):
                candle(**changes)


if __name__ == "__main__":
    unittest.main()
