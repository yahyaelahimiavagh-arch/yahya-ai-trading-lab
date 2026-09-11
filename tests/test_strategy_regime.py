import contextlib
import io
import unittest
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from unittest.mock import patch

from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.backtest import MarketSnapshot
from yatl.strategy import (StrategyContext, StrategyIdentity, MarketRegime,
                           RegimeError, RegimeReason, classify_regime)
from yatl.strategy.regime import _classify

END = 1_700_006_400_000


def context(prices, symbol="BTCUSDT", decision=END):
    def bars(interval, values):
        duration = INTERVAL_MILLISECONDS[interval]
        boundary = decision // duration * duration
        return tuple(Candle(
            DATA_SOURCE, symbol, interval, boundary - (len(values)-i)*duration,
            boundary - (len(values)-i-1)*duration - 1,
            str(p), str(p), str(p), str(p), "1", "100", 1, True,
        ) for i, p in enumerate(values))
    snapshot = MarketSnapshot(symbol, decision, bars("1h", [100]),
                              bars("15m", [100]), bars("4h", prices))
    return StrategyContext(StrategyIdentity("RESEARCH_REGIME", "1.0.0"), snapshot)


class RegimeTests(unittest.TestCase):
    @patch("yatl.__main__.load_accepted_dataset")
    @patch("yatl.__main__.latest_spec_from_manifest")
    @patch("sys.argv", ["yatl", "strategy-regime-check"])
    def test_cli_replays_both_symbols(self, latest, load):
        from yatl.__main__ import main
        from types import SimpleNamespace
        latest.return_value = SimpleNamespace(start_time_ms=END)
        load.side_effect = [
            SimpleNamespace(snapshot_at=lambda t: context([100]*51).snapshot),
            SimpleNamespace(snapshot_at=lambda t: context([100]*51, "ETHUSDT").snapshot),
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertIn("BTCUSDT 4h regime=RANGE", output.getvalue())
        self.assertIn("ETHUSDT 4h regime=RANGE", output.getvalue())
        self.assertIn("LIVE_MASTER_LOCK=OFF", output.getvalue())

    def test_future_append_does_not_change_visible_prefix(self):
        ctx = context(list(range(100,151)))
        rows = ctx.snapshot.regime
        last = rows[-1]
        future = replace(last, open_time_ms=last.open_time_ms+14_400_000,
                         close_time_ms=last.close_time_ms+14_400_000,
                         open="999", high="999", low="999", close="999")
        extended = rows + (future,)
        visible = tuple(c for c in extended if c.close_time_ms < END)
        same = replace(ctx, snapshot=replace(ctx.snapshot, regime=visible))
        self.assertEqual(classify_regime(ctx), classify_regime(same))

    def test_hand_computed_up_down_flat(self):
        for symbol in ("BTCUSDT", "ETHUSDT"):
            up = classify_regime(context(list(range(100,151)), symbol))
            self.assertEqual(up.regime, MarketRegime.TREND_UP)
            self.assertEqual(up.fast_sma, Decimal("140.5"))
            self.assertEqual(up.slow_sma, Decimal("125.5"))
            down = classify_regime(context(list(range(150,99,-1)), symbol))
            self.assertEqual(down.regime, MarketRegime.TREND_DOWN)
            flat = classify_regime(context([100]*51, symbol))
            self.assertEqual(flat.regime, MarketRegime.RANGE)
            self.assertEqual(flat.relative_slope, 0)

    def test_exact_boundaries_and_conflict(self):
        d = Decimal
        for spread in ("0.002", "-0.002"):
            for slope in ("0.0005", "-0.0005"):
                self.assertEqual(_classify(d(100),d(100),d(100),d(spread),d(slope))[0],
                                 MarketRegime.RANGE)
        for spread, slope, price in (("0.0021","0","110"),
                                      ("0.0021","0.001","100"),
                                      ("0.001","0.000501","110")):
            self.assertEqual(_classify(d(price),d(100),d(100),d(spread),d(slope))[0],
                             MarketRegime.UNKNOWN)
        self.assertEqual(_classify(d(110),d(100),d(100),d(".0021"),d(".001"))[0],
                         MarketRegime.TREND_UP)

    def test_warmup(self):
        for count in (1, 20, 50):
            result = classify_regime(context([100]*count))
            self.assertEqual(result.reason, RegimeReason.INSUFFICIENT_HISTORY)
            self.assertIsNone(result.fast_sma)
        self.assertEqual(classify_regime(context([100]*51)).regime, MarketRegime.RANGE)

    def test_prefix_replay_and_timeframe_isolation(self):
        original = context(list(range(100,151)))
        # Same legal 4h prefix at the next 1h decision gives identical measures.
        later = context(list(range(100,151)), decision=END+3_600_000)
        first, second = classify_regime(original), classify_regime(later)
        self.assertEqual((first.regime,first.relative_spread,first.relative_slope),
                         (second.regime,second.relative_spread,second.relative_slope))
        changed = replace(original.snapshot,
                          primary=tuple(replace(c, open="200", high="200",
                                                low="200", close="200")
                                        for c in original.snapshot.primary))
        self.assertEqual(classify_regime(replace(original,snapshot=changed)).regime,
                         first.regime)
        self.assertEqual(first, classify_regime(original))

    def test_corrupt_future_open_gap_symbol_rejected(self):
        for change in ("future", "open", "gap", "symbol", "interval"):
            ctx = context([100]*51)
            rows = ctx.snapshot.regime
            if change == "future":
                last = rows[-1]
                rows += (replace(last, open_time_ms=last.open_time_ms+14_400_000,
                                 close_time_ms=last.close_time_ms+14_400_000),)
            elif change == "open":
                rows = rows[:-1]+(replace(rows[-1],is_closed=False),)
            elif change == "gap":
                rows = rows[:10]+rows[11:]
            elif change == "symbol":
                rows = rows[:-1]+(replace(rows[-1],symbol="ETHUSDT"),)
            else:
                rows = ctx.snapshot.primary
            object.__setattr__(ctx.snapshot, "regime", rows)
            with self.subTest(change=change), self.assertRaises(RegimeError):
                classify_regime(ctx)

    def test_immutable_and_tamper_checked(self):
        result = classify_regime(context([100]*51))
        with self.assertRaises(FrozenInstanceError):
            result.version = "changed"
        for change in ({"regime":MarketRegime.TREND_UP}, {"version":"v2"},
                       {"fast_sma":Decimal(99)}, {"relative_slope":0.0}):
            with self.assertRaises(RegimeError):
                replace(result, **change)
        with self.assertRaises(RegimeError):
            classify_regime(object())


if __name__ == "__main__":
    unittest.main()
