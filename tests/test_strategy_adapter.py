import inspect
import unittest
from dataclasses import replace

from yatl.backtest import (BacktestSpec, DecisionEvent, FillReason,
                           IntentAction, MarketSnapshot, PortfolioLedger,
                           apply_costs)
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.strategy import (BREAKOUT_IDENTITY, DecisionReason,
                           FIXED_RESEARCH_QUANTITY, LongSetup,
                           ResearchSignalAdapter, SignalAdapterError,
                           StrategyAction, StrategyContext, StrategyDecision,
                           StrategyIdentity, TREND_PULLBACK_IDENTITY)


START = 1_699_999_200_000


def candle(interval, opened, *, symbol="BTCUSDT", price="100",
           low="99", high="106", volume="10"):
    duration = INTERVAL_MILLISECONDS[interval]
    return Candle(DATA_SOURCE, symbol, interval, opened, opened + duration - 1,
                  price, high, low, price, volume, "1000", 20, True)


def event(sequence, *, symbol="BTCUSDT"):
    decision = START + sequence * INTERVAL_MILLISECONDS["1h"]

    def history(interval):
        duration = INTERVAL_MILLISECONDS[interval]
        opened = (decision // duration) * duration - duration
        return (candle(interval, opened, symbol=symbol),)

    snapshot = MarketSnapshot(symbol, decision, history("1h"),
                              history("15m"), history("4h"))
    return DecisionEvent(sequence, decision, decision, snapshot)


def fill_bar(item, **changes):
    values = {"symbol": item.snapshot.symbol, "price": "100",
              "low": "99", "high": "106", "volume": "10"}
    values.update(changes)
    return candle("1h", item.decision_time_ms, **values)


def decision(item, action, reason, setup=None, identity=TREND_PULLBACK_IDENTITY):
    context = StrategyContext(identity, item.snapshot)
    return StrategyDecision(context, action, reason, setup)


def entry(item, identity=TREND_PULLBACK_IDENTITY):
    reason = (DecisionReason.TREND_PULLBACK_ENTRY
              if identity == TREND_PULLBACK_IDENTITY
              else DecisionReason.BREAKOUT_ENTRY)
    return decision(item, StrategyAction.ENTER_LONG, reason,
                    LongSetup("100", "95", "110"), identity)


class SignalAdapterTests(unittest.TestCase):
    def test_runtime_cli_reports_costed_flat_lifecycle(self):
        from yatl.__main__ import main
        from unittest.mock import patch
        import contextlib
        import io

        output = io.StringIO()
        with patch("sys.argv", ["yatl", "strategy-adapter-check"]), \
                contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("intents=ENTER_LONG/EXIT_LONG", text)
        self.assertIn("fixed_quantity=0.001 flat=true", text)
        self.assertIn("costs_applied=true closed_trades=1 replay_equal=true", text)
        self.assertIn("LIVE_MASTER_LOCK=OFF", text)

    def test_no_trade_entry_hold_exit_lifecycle(self):
        adapter = ResearchSignalAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        first_event = event(0)
        no_trade = adapter.process(
            first_event,
            decision(first_event, StrategyAction.NO_TRADE,
                     DecisionReason.SETUP_ABSENT),
            fill_bar(first_event))
        self.assertEqual(no_trade.intent.action, IntentAction.HOLD)
        self.assertEqual(no_trade.fills, ())
        self.assertFalse(adapter.has_position)

        entry_event = event(1)
        entered = adapter.process(entry_event, entry(entry_event),
                                  fill_bar(entry_event))
        self.assertEqual(entered.intent.quantity, FIXED_RESEARCH_QUANTITY)
        self.assertEqual(entered.fills[0].reason, FillReason.NEXT_PRIMARY_OPEN)
        self.assertTrue(adapter.has_position)
        self.assertEqual(adapter.active_setup, entry(entry_event).setup)

        hold_event = event(2)
        held = adapter.process(
            hold_event,
            decision(hold_event, StrategyAction.NO_TRADE,
                     DecisionReason.HOLD_POSITION),
            fill_bar(hold_event))
        self.assertEqual((held.intent.action, held.fills),
                         (IntentAction.HOLD, ()))
        self.assertTrue(adapter.has_position)

        exit_event = event(3)
        exited = adapter.process(
            exit_event,
            decision(exit_event, StrategyAction.EXIT_LONG,
                     DecisionReason.STRATEGY_EXIT),
            fill_bar(exit_event, price="102", low="101", high="103"))
        self.assertEqual(exited.fills[0].reason, FillReason.SCRIPTED_EXIT)
        self.assertFalse(adapter.has_position)

    def test_duplicate_and_overlapping_entries_are_rejected_atomically(self):
        adapter = ResearchSignalAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        first = event(0)
        adapter.process(first, entry(first), fill_bar(first))
        with self.assertRaises(SignalAdapterError):
            adapter.process(first, entry(first), fill_bar(first))
        second = event(1)
        with self.assertRaises(SignalAdapterError):
            adapter.process(second, entry(second), fill_bar(second))
        self.assertTrue(adapter.has_position)
        held = adapter.process(
            second,
            decision(second, StrategyAction.NO_TRADE,
                     DecisionReason.HOLD_POSITION),
            fill_bar(second))
        self.assertEqual(held.intent.action, IntentAction.HOLD)

    def test_flat_hold_and_exit_are_rejected(self):
        for action, reason in (
                (StrategyAction.NO_TRADE, DecisionReason.HOLD_POSITION),
                (StrategyAction.EXIT_LONG, DecisionReason.STRATEGY_EXIT)):
            adapter = ResearchSignalAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
            first = event(0)
            with self.assertRaises(SignalAdapterError):
                adapter.process(first, decision(first, action, reason),
                                fill_bar(first))
            self.assertFalse(adapter.has_position)

    def test_p2_ambiguous_bar_keeps_stop_priority_and_closes_state(self):
        adapter = ResearchSignalAdapter(BREAKOUT_IDENTITY, "BTCUSDT")
        first = event(0)
        adapter.process(first, entry(first, BREAKOUT_IDENTITY), fill_bar(first))
        second = event(1)
        stopped = adapter.process(
            second,
            decision(second, StrategyAction.NO_TRADE,
                     DecisionReason.HOLD_POSITION, identity=BREAKOUT_IDENTITY),
            fill_bar(second, low="94", high="111"))
        self.assertEqual(stopped.fills[0].reason,
                         FillReason.AMBIGUOUS_STOP_PRIORITY)
        self.assertFalse(adapter.has_position)

    def test_explicit_costs_finish_with_flat_portfolio(self):
        adapter = ResearchSignalAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        first, second = event(0), event(1)
        entered = adapter.process(first, entry(first), fill_bar(first))
        exited = adapter.process(
            second,
            decision(second, StrategyAction.EXIT_LONG,
                     DecisionReason.STRATEGY_EXIT),
            fill_bar(second, price="105", low="104", high="106"))
        spec = BacktestSpec("BTCUSDT", START, START + 2 * 3_600_000,
                            initial_cash="1000", fee_bps="10",
                            slippage_bps="5")
        ledger = PortfolioLedger(spec)
        references = entered.fills + exited.fills
        ledger.apply_many(tuple(apply_costs(item, spec) for item in references))
        final = ledger.snapshot("105")
        self.assertEqual(final.asset_quantity, 0)
        self.assertEqual(final.closed_trades, 1)
        self.assertGreater(final.total_fee_quote, 0)
        self.assertGreater(final.total_slippage_quote, 0)

    def test_failed_p2_fill_does_not_consume_event_or_open_state(self):
        adapter = ResearchSignalAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        first = event(0)
        with self.assertRaises(SignalAdapterError):
            adapter.process(first, entry(first),
                            fill_bar(first, price="111", low="109", high="112"))
        self.assertFalse(adapter.has_position)
        accepted = adapter.process(first, entry(first), fill_bar(first))
        self.assertEqual(len(accepted.fills), 1)
        self.assertTrue(adapter.has_position)

    def test_mismatched_identity_symbol_snapshot_and_order_fail(self):
        with self.assertRaises(SignalAdapterError):
            ResearchSignalAdapter(StrategyIdentity("OTHER_STRATEGY", "1.0.0"),
                                  "BTCUSDT")
        with self.assertRaises(SignalAdapterError):
            ResearchSignalAdapter(TREND_PULLBACK_IDENTITY, "BNBUSDT")
        adapter = ResearchSignalAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
        second = event(1)
        with self.assertRaises(SignalAdapterError):
            adapter.process(second, entry(second), fill_bar(second))
        first = event(0)
        wrong = decision(first, StrategyAction.NO_TRADE,
                         DecisionReason.SETUP_ABSENT,
                         identity=BREAKOUT_IDENTITY)
        with self.assertRaises(SignalAdapterError):
            adapter.process(first, wrong, fill_bar(first))

    def test_replay_is_byte_for_byte_equal(self):
        def replay():
            adapter = ResearchSignalAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
            first, second = event(0), event(1)
            one = adapter.process(first, entry(first), fill_bar(first))
            two = adapter.process(
                second,
                decision(second, StrategyAction.EXIT_LONG,
                         DecisionReason.STRATEGY_EXIT),
                fill_bar(second, price="105", low="104", high="106"))
            return one, two, adapter.has_position

        self.assertEqual(replay(), replay())

    def test_quantity_is_fixed_and_not_a_constructor_input(self):
        parameters = inspect.signature(ResearchSignalAdapter).parameters
        self.assertEqual(tuple(parameters), ("identity", "symbol"))
        self.assertEqual(FIXED_RESEARCH_QUANTITY, "0.001")


if __name__ == "__main__":
    unittest.main()
