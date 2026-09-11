import unittest
import contextlib
import io
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from types import SimpleNamespace
from unittest.mock import patch

from yatl.backtest import BacktestContractError, MarketSnapshot
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.strategy import (DecisionReason, LongSetup, StrategyAction,
                           StrategyContext, StrategyIdentity,
                           TREND_PULLBACK_CONFIGURATION,
                           TREND_PULLBACK_IDENTITY, TrendStrategyError,
                           evaluate_trend_pullback)


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


def context(*, primary=None, confirmation=True, regime=None):
    primary = primary or bars("1h", range(100, 120),
                              last={"open": "118", "high": "121",
                                    "low": "109", "close": "119"})
    context_rows = bars("15m", [117, 118],
                        last={"open": "117", "high": "119",
                              "low": "116", "close": "118"})
    if not confirmation:
        context_rows = bars("15m", [118, 117],
                            last={"open": "118", "high": "119",
                                  "low": "116", "close": "117"})
    regime = regime or bars("4h", range(100, 151))
    snapshot = MarketSnapshot("BTCUSDT", DECISION, primary, context_rows, regime)
    return StrategyContext(TREND_PULLBACK_IDENTITY, snapshot)


class TrendPullbackTests(unittest.TestCase):
    @patch("yatl.__main__.load_accepted_dataset")
    @patch("yatl.__main__.latest_spec_from_manifest")
    @patch("sys.argv", ["yatl", "strategy-trend-check"])
    def test_cli_replays_accepted_symbol_views(self, latest, load):
        from yatl.__main__ import main
        latest.return_value = SimpleNamespace(start_time_ms=DECISION)
        load.side_effect = [
            SimpleNamespace(snapshot_at=lambda _: context().snapshot),
            SimpleNamespace(snapshot_at=lambda _: replace(
                context().snapshot, symbol="ETHUSDT",
                primary=bars("1h", range(100, 120),
                             last={"open": "118", "high": "121",
                                   "low": "109", "close": "119"},
                             symbol="ETHUSDT"),
                context=bars("15m", [117, 118], symbol="ETHUSDT"),
                regime=bars("4h", range(100, 151), symbol="ETHUSDT"))),
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("BTCUSDT action=ENTER_LONG", text)
        self.assertIn("ETHUSDT action=ENTER_LONG", text)
        self.assertIn("replay_equal=true", text)
        self.assertIn("LIVE_MASTER_LOCK=OFF", text)

    def test_positive_entry_has_exact_visible_levels(self):
        decision = evaluate_trend_pullback(context())
        self.assertEqual(decision.action, StrategyAction.ENTER_LONG)
        self.assertEqual(decision.reason, DecisionReason.TREND_PULLBACK_ENTRY)
        self.assertEqual(decision.setup.reference_price, "119")
        self.assertLess(Decimal(decision.setup.invalidation_price), Decimal("109"))
        with localcontext() as arithmetic:
            arithmetic.prec = 50
            risk = Decimal("119") - Decimal(decision.setup.invalidation_price)
            self.assertEqual(Decimal(decision.setup.target_price), Decimal("119") + 2 * risk)
        self.assertEqual(decision.context.identity, TREND_PULLBACK_IDENTITY)

    def test_regime_blocks_entry_and_unknown_is_explicit(self):
        blocked = evaluate_trend_pullback(context(regime=bars("4h", [100] * 51)))
        self.assertEqual((blocked.action, blocked.reason),
                         (StrategyAction.NO_TRADE, DecisionReason.REGIME_BLOCKED))
        insufficient = evaluate_trend_pullback(context(regime=bars("4h", [100] * 50)))
        self.assertEqual(insufficient.reason, DecisionReason.INSUFFICIENT_HISTORY)
        conflicting_prices = [100] * 31 + [110] * 20
        unknown = evaluate_trend_pullback(context(regime=bars("4h", conflicting_prices)))
        self.assertIn(unknown.reason, (DecisionReason.REGIME_UNKNOWN,
                                      DecisionReason.REGIME_BLOCKED))

    def test_setup_and_confirmation_fail_closed(self):
        absent_primary = bars("1h", range(100, 120),
                              last={"open": "118", "high": "122",
                                    "low": "118", "close": "119"})
        absent = evaluate_trend_pullback(context(primary=absent_primary))
        self.assertEqual(absent.reason, DecisionReason.SETUP_ABSENT)
        failed = evaluate_trend_pullback(context(confirmation=False))
        self.assertEqual(failed.reason, DecisionReason.CONFIRMATION_FAILED)

    def test_warmup_is_explicit(self):
        short = bars("1h", range(100, 119))
        result = evaluate_trend_pullback(context(primary=short))
        self.assertEqual((result.action, result.reason),
                         (StrategyAction.NO_TRADE, DecisionReason.INSUFFICIENT_HISTORY))

    def test_hold_and_explicit_exit_rules(self):
        entry = evaluate_trend_pullback(context())
        held = evaluate_trend_pullback(context(), in_position=True,
                                       active_setup=entry.setup)
        self.assertEqual((held.action, held.reason),
                         (StrategyAction.NO_TRADE, DecisionReason.HOLD_POSITION))
        broken = bars("1h", list(range(100, 119)) + [50],
                      last={"open": "60", "high": "61", "low": "49", "close": "50"})
        exit_decision = evaluate_trend_pullback(
            context(primary=broken), in_position=True, active_setup=entry.setup)
        self.assertEqual((exit_decision.action, exit_decision.reason),
                         (StrategyAction.EXIT_LONG, DecisionReason.STRATEGY_EXIT))
        regime_exit = evaluate_trend_pullback(
            context(regime=bars("4h", [100] * 51)), in_position=True,
            active_setup=entry.setup)
        self.assertEqual(regime_exit.action, StrategyAction.EXIT_LONG)

    def test_state_identity_and_mutation_are_rejected(self):
        valid = context()
        setup = LongSetup("119", "100", "157")
        invalid = (
            {"in_position": 1, "active_setup": setup},
            {"in_position": True, "active_setup": None},
            {"in_position": False, "active_setup": setup},
        )
        for state in invalid:
            with self.assertRaises(TrendStrategyError):
                evaluate_trend_pullback(valid, **state)
        wrong = replace(valid, identity=StrategyIdentity("OTHER_STRATEGY", "1.0.0"))
        with self.assertRaises(TrendStrategyError):
            evaluate_trend_pullback(wrong)
        with self.assertRaises(FrozenInstanceError):
            TREND_PULLBACK_CONFIGURATION.values = ()

    def test_gap_current_and_future_candles_never_reach_strategy(self):
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
        before = evaluate_trend_pullback(valid)
        future = replace(current, open="999", high="1000", low="998", close="999")
        visible = tuple(row for row in valid.snapshot.primary + (future,)
                        if row.close_time_ms < DECISION)
        replay = evaluate_trend_pullback(
            replace(valid, snapshot=replace(valid.snapshot, primary=visible)))
        self.assertEqual(before, replay)

    def test_replay_is_deterministic_and_has_frozen_digest(self):
        first = evaluate_trend_pullback(context())
        second = evaluate_trend_pullback(context())
        self.assertEqual(first, second)
        self.assertEqual(first.context_sha256, second.context_sha256)
        self.assertEqual(len(TREND_PULLBACK_CONFIGURATION.sha256), 64)


if __name__ == "__main__":
    unittest.main()
