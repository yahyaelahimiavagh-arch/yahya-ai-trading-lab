import contextlib
import io
import unittest
from dataclasses import replace
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import (BacktestConfigError, BacktestContractError,
                           BacktestSpec, MarketSnapshot)
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS


DECISION = 1_699_999_200_000


def candle(interval, open_time, *, symbol="BTCUSDT", closed=True):
    duration = INTERVAL_MILLISECONDS[interval]
    return Candle(
        source=DATA_SOURCE, symbol=symbol, interval=interval,
        open_time_ms=open_time, close_time_ms=open_time + duration - 1,
        open="100", high="110", low="90", close="105",
        base_volume="10", quote_volume="1000", trade_count=20,
        is_closed=closed,
    )


def history(interval, count=2):
    duration = INTERVAL_MILLISECONDS[interval]
    last = (DECISION // duration) * duration - duration
    return tuple(candle(interval, last - index * duration)
                 for index in reversed(range(count)))


def snapshot(**changes):
    values = {
        "symbol": "BTCUSDT", "decision_time_ms": DECISION,
        "primary": history("1h"), "context": history("15m"),
        "regime": history("4h"),
    }
    values.update(changes)
    return MarketSnapshot(**values)


class BacktestSpecTests(unittest.TestCase):
    def test_fixed_safe_spot_policy(self):
        spec = BacktestSpec("BTCUSDT", DECISION, DECISION + 86_400_000)
        self.assertEqual(str(spec.cash_decimal), "10000")
        self.assertEqual(str(spec.fee_bps_decimal), "10")
        self.assertEqual(str(spec.slippage_bps_decimal), "5")
        self.assertEqual(spec.execution_price_policy, "NEXT_PRIMARY_OPEN")

    def test_range_symbol_decimal_and_seed_fail_closed(self):
        valid = BacktestSpec("BTCUSDT", DECISION, DECISION + 3_600_000)
        mutations = {
            "symbol": "BNBUSDT", "start_time_ms": DECISION + 1,
            "end_time_ms": DECISION, "initial_cash": "0", "fee_bps": "1001",
            "slippage_bps": "NaN", "seed": -1,
        }
        for field, value in mutations.items():
            with self.subTest(field=field), self.assertRaises(BacktestConfigError):
                replace(valid, **{field: value})

        for initial_cash in ("1e4", "+10000", "01", "1000000000000001"):
            with self.subTest(initial_cash=initial_cash), self.assertRaises(BacktestConfigError):
                replace(valid, initial_cash=initial_cash)
        with self.assertRaises(BacktestConfigError):
            replace(valid, end_time_ms=DECISION + 100_001 * 3_600_000)

    def test_execution_safety_switches_cannot_be_relaxed(self):
        valid = BacktestSpec("ETHUSDT", DECISION, DECISION + 3_600_000)
        for field, value in (("paper_only", False), ("live_master_lock", "ON"),
                             ("spot_only", False), ("allow_short", True),
                             ("allow_leverage", True),
                             ("execution_price_policy", "CLOSE")):
            with self.subTest(field=field), self.assertRaises(BacktestConfigError):
                replace(valid, **{field: value})


class MarketSnapshotTests(unittest.TestCase):
    def test_valid_snapshot_exposes_only_latest_completed_candles(self):
        view = snapshot()
        self.assertEqual(view.latest_primary.close_time_ms, DECISION - 1)
        self.assertEqual(view.latest_context.close_time_ms, DECISION - 1)
        self.assertLess(view.latest_regime.close_time_ms, DECISION)

    def test_future_open_stale_wrong_identity_and_wrong_type_fail_closed(self):
        primary = history("1h")
        cases = (
            {"primary": primary[:-1] + (candle("1h", DECISION, closed=False),)},
            {"primary": (replace(primary[-1], is_closed=False),)},
            {"primary": primary[:-1]},
            {"primary": (candle("1h", primary[-1].open_time_ms, symbol="ETHUSDT"),)},
            {"primary": list(primary)},
        )
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(BacktestContractError):
                snapshot(**changes)

    def test_unordered_gapped_and_unaligned_decisions_fail_closed(self):
        primary = history("1h", 3)
        for changes in (
            {"primary": (primary[1], primary[0], primary[2])},
            {"primary": (primary[0], primary[2])},
            {"decision_time_ms": DECISION + 1},
            {"decision_time_ms": True},
        ):
            with self.subTest(changes=changes), self.assertRaises(BacktestContractError):
                snapshot(**changes)

    @patch("sys.argv", ["yatl", "backtest-contract-check"])
    def test_runtime_cli_reports_safe_local_contract(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("point-in-time backtest contract", text)
        self.assertIn("NEXT_PRIMARY_OPEN", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
