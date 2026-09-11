import contextlib
import io
import unittest
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from yatl.backtest import BacktestContractError, MarketSnapshot
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.strategy import (BREAKOUT_CONFIGURATION, BREAKOUT_IDENTITY,
                           BreakoutStrategyError, DecisionReason, LongSetup,
                           StrategyAction, StrategyContext, StrategyIdentity,
                           evaluate_breakout)


DECISION = 1_700_006_400_000


def bars(interval, closes, *, last=None, symbol="BTCUSDT"):
    duration = INTERVAL_MILLISECONDS[interval]
    boundary = DECISION // duration * duration
    result = []
    for index, value in enumerate(closes):
        close = Decimal(str(value))
        opened = boundary - (len(closes) - index) * duration
        fields = {
            "open": str(close - 1), "high": str(close + 2),
            "low": str(close - 2), "close": str(close),
        }
        if index == len(closes) - 1 and last:
            fields.update(last)
        result.append(Candle(
            DATA_SOURCE, symbol, interval, opened, opened + duration - 1,
            fields["open"], fields["high"], fields["low"], fields["close"],
            "10", "1000", 20, True,
        ))
    return tuple(result)


def context(*, primary=None, confirmation=True, regime=None, symbol="BTCUSDT"):
    primary = primary or bars(
        "1h", [100] * 20 + [103], symbol=symbol,
        last={"open": "102", "high": "103.5", "low": "101", "close": "103"})
    confirmation_rows = bars("15m", [102, 103], symbol=symbol)
    if not confirmation:
        confirmation_rows = bars(
            "15m", [103, 102], symbol=symbol,
            last={"open": "103", "high": "104", "low": "101", "close": "102"})
    regime = regime or bars("4h", range(100, 151), symbol=symbol)
    snapshot = MarketSnapshot(symbol, DECISION, primary, confirmation_rows, regime)
    return StrategyContext(BREAKOUT_IDENTITY, snapshot)


class BreakoutTests(unittest.TestCase):
    @patch("yatl.__main__.load_accepted_dataset")
    @patch("yatl.__main__.latest_spec_from_manifest")
    @patch("sys.argv", ["yatl", "strategy-breakout-check"])
    def test_cli_replays_both_symbols(self, latest, load):
        from yatl.__main__ import main
        latest.return_value = SimpleNamespace(start_time_ms=DECISION)
        load.side_effect = [
            SimpleNamespace(snapshot_at=lambda _: context().snapshot),
            SimpleNamespace(snapshot_at=lambda _: context(symbol="ETHUSDT").snapshot),
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("BTCUSDT action=ENTER_LONG", text)
        self.assertIn("ETHUSDT action=ENTER_LONG", text)
        self.assertIn("replay_equal=true", text)
        self.assertIn("LIVE_MASTER_LOCK=OFF", text)

    def test_confirmed_breakout_emits_exact_levels(self):
        decision = evaluate_breakout(context())
        self.assertEqual((decision.action, decision.reason),
                         (StrategyAction.ENTER_LONG, DecisionReason.BREAKOUT_ENTRY))
        self.assertEqual(decision.setup, LongSetup("103", "100", "109"))

    def test_false_breakout_and_range_are_blocked(self):
        false_breakout = bars(
            "1h", [100] * 20 + [102],
            last={"open": "101", "high": "103", "low": "100", "close": "102"})
        absent = evaluate_breakout(context(primary=false_breakout))
        self.assertEqual(absent.reason, DecisionReason.SETUP_ABSENT)
        ranged = evaluate_breakout(context(regime=bars("4h", [100] * 51)))
        self.assertEqual(ranged.reason, DecisionReason.REGIME_BLOCKED)
        unknown = evaluate_breakout(
            context(regime=bars("4h", [100] * 31 + [110] * 20)))
        self.assertEqual(unknown.reason, DecisionReason.REGIME_UNKNOWN)

    def test_low_quality_and_overextended_breakouts_are_rejected(self):
        low_quality = bars(
            "1h", [100] * 20 + [103],
            last={"open": "102", "high": "110", "low": "100", "close": "103"})
        extended = bars(
            "1h", [100] * 20 + [110],
            last={"open": "109", "high": "110.25", "low": "109", "close": "110"})
        for rows in (low_quality, extended):
            with self.subTest(close=rows[-1].close):
                result = evaluate_breakout(context(primary=rows))
                self.assertEqual((result.action, result.reason),
                                 (StrategyAction.NO_TRADE, DecisionReason.SETUP_ABSENT))

    def test_confirmation_and_warmup_are_explicit(self):
        failed = evaluate_breakout(context(confirmation=False))
        self.assertEqual(failed.reason, DecisionReason.CONFIRMATION_FAILED)
        short = evaluate_breakout(context(primary=bars("1h", [100] * 20)))
        self.assertEqual(short.reason, DecisionReason.INSUFFICIENT_HISTORY)
        short_regime = evaluate_breakout(context(regime=bars("4h", [100] * 50)))
        self.assertEqual(short_regime.reason, DecisionReason.INSUFFICIENT_HISTORY)

    def test_hold_and_deterministic_exit_rules(self):
        entry = evaluate_breakout(context())
        held = evaluate_breakout(context(), in_position=True, active_setup=entry.setup)
        self.assertEqual((held.action, held.reason),
                         (StrategyAction.NO_TRADE, DecisionReason.HOLD_POSITION))
        failed_range = bars(
            "1h", [100] * 20 + [101],
            last={"open": "102", "high": "103", "low": "100", "close": "101"})
        exited = evaluate_breakout(context(primary=failed_range),
                                   in_position=True, active_setup=entry.setup)
        self.assertEqual((exited.action, exited.reason),
                         (StrategyAction.EXIT_LONG, DecisionReason.STRATEGY_EXIT))
        regime_exit = evaluate_breakout(
            context(regime=bars("4h", [100] * 51)),
            in_position=True, active_setup=entry.setup)
        self.assertEqual(regime_exit.action, StrategyAction.EXIT_LONG)

    def test_state_identity_and_configuration_are_immutable(self):
        valid = context()
        setup = LongSetup("103", "100", "109")
        for state in (
                {"in_position": 1, "active_setup": setup},
                {"in_position": True, "active_setup": None},
                {"in_position": False, "active_setup": setup}):
            with self.assertRaises(BreakoutStrategyError):
                evaluate_breakout(valid, **state)
        wrong = replace(valid, identity=StrategyIdentity("TREND_PULLBACK", "1.0.0"))
        with self.assertRaises(BreakoutStrategyError):
            evaluate_breakout(wrong)
        with self.assertRaises(FrozenInstanceError):
            BREAKOUT_CONFIGURATION.values = ()

    def test_gap_current_and_future_are_rejected_or_invisible(self):
        valid = context()
        with self.assertRaises(BacktestContractError):
            replace(valid.snapshot, primary=valid.snapshot.primary[:5]
                    + valid.snapshot.primary[6:])
        latest = valid.snapshot.primary[-1]
        current = replace(latest,
                          open_time_ms=latest.open_time_ms + 3_600_000,
                          close_time_ms=latest.close_time_ms + 3_600_000)
        with self.assertRaises(BacktestContractError):
            replace(valid.snapshot, primary=valid.snapshot.primary[:-1] + (current,))
        before = evaluate_breakout(valid)
        future = replace(current, open="999", high="1000", low="998", close="999")
        visible = tuple(row for row in valid.snapshot.primary + (future,)
                        if row.close_time_ms < DECISION)
        replay = evaluate_breakout(
            replace(valid, snapshot=replace(valid.snapshot, primary=visible)))
        self.assertEqual(before, replay)

    def test_replay_and_candidate_identity_are_independent(self):
        first = evaluate_breakout(context())
        second = evaluate_breakout(context())
        self.assertEqual(first, second)
        self.assertEqual(first.strategy_id, "RANGE_BREAKOUT")
        self.assertNotEqual(first.strategy_id, "TREND_PULLBACK")
        self.assertEqual(len(BREAKOUT_CONFIGURATION.sha256), 64)


if __name__ == "__main__":
    unittest.main()
