import contextlib
import io
import unittest
from dataclasses import fields, replace
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import MarketSnapshot
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.strategy import (DecisionReason, LongSetup, StrategyAction,
                           StrategyContext, StrategyContractError,
                           StrategyDecision, StrategyIdentity)


DECISION = 1_699_999_200_000


def candles(interval, count=2, close="105"):
    duration = INTERVAL_MILLISECONDS[interval]
    start = (DECISION // duration) * duration - count * duration
    return tuple(Candle(
        DATA_SOURCE, "BTCUSDT", interval, opened, opened + duration - 1,
        "100", "110", "90", close, "10", "1000", 20, True,
    ) for opened in range(start, start + count * duration, duration))


def context(**changes):
    snapshot = MarketSnapshot("BTCUSDT", DECISION, candles("1h"),
                              candles("15m"), candles("4h"))
    values = {"identity": StrategyIdentity("TREND_PULLBACK", "1.0.0"),
              "snapshot": snapshot}
    values.update(changes)
    return StrategyContext(**values)


class StrategyContractTests(unittest.TestCase):
    def test_context_identity_and_digest_are_deterministic(self):
        first = context()
        second = context()
        self.assertEqual(first, second)
        self.assertEqual(first.context_sha256, second.context_sha256)
        self.assertEqual(len(first.context_sha256), 64)
        self.assertEqual((first.symbol, first.decision_time_ms), ("BTCUSDT", DECISION))

    def test_material_visible_data_changes_context_digest(self):
        first = context()
        changed_snapshot = replace(first.snapshot, primary=candles("1h", close="106"))
        second = replace(first, snapshot=changed_snapshot)
        self.assertNotEqual(first.context_sha256, second.context_sha256)

    def test_explicit_no_trade_decision(self):
        decision = StrategyDecision(context(), StrategyAction.NO_TRADE,
                                    DecisionReason.SETUP_ABSENT)
        self.assertEqual(decision.strategy_id, "TREND_PULLBACK")
        self.assertIsNone(decision.setup)

    def test_entry_and_exit_decisions(self):
        setup = LongSetup("105", "100", "115")
        entry = StrategyDecision(context(), StrategyAction.ENTER_LONG,
                                 DecisionReason.TREND_PULLBACK_ENTRY, setup)
        exit_decision = StrategyDecision(context(), StrategyAction.EXIT_LONG,
                                         DecisionReason.STRATEGY_EXIT)
        self.assertEqual(entry.setup, setup)
        self.assertIsNone(exit_decision.setup)

    def test_invalid_identity_and_levels_fail_closed(self):
        for identity in (("bad", "1.0.0"), ("VALID_ID", "v1"), ("AB", "1.0.0")):
            with self.subTest(identity=identity), self.assertRaises(StrategyContractError):
                StrategyIdentity(*identity)
        for levels in (("105", "105", "115"), ("105", "100", "100"),
                       ("1e2", "90", "110"), (100.0, "90", "110")):
            with self.subTest(levels=levels), self.assertRaises(StrategyContractError):
                LongSetup(*levels)

    def test_action_reason_setup_mismatches_fail_closed(self):
        setup = LongSetup("105", "100", "115")
        invalid = (
            (StrategyAction.ENTER_LONG, DecisionReason.SETUP_ABSENT, setup),
            (StrategyAction.ENTER_LONG, DecisionReason.BREAKOUT_ENTRY, None),
            (StrategyAction.EXIT_LONG, DecisionReason.STRATEGY_EXIT, setup),
            (StrategyAction.NO_TRADE, DecisionReason.TREND_PULLBACK_ENTRY, None),
        )
        for action, reason, item in invalid:
            with self.subTest(action=action), self.assertRaises(StrategyContractError):
                StrategyDecision(context(), action, reason, item)

    def test_safety_policy_tampering_fails_closed(self):
        valid = context()
        for changes in ({"paper_only": False}, {"live_master_lock": "ON"},
                        {"spot_only": False}, {"allow_short": True},
                        {"allow_leverage": True}):
            with self.subTest(changes=changes), self.assertRaises(StrategyContractError):
                replace(valid, **changes)

    def test_contract_has_no_execution_or_sizing_fields(self):
        names = {item.name for contract in (StrategyContext, LongSetup, StrategyDecision)
                 for item in fields(contract)}
        forbidden = {"quantity", "order", "broker", "api_key", "api_secret",
                     "leverage", "account_balance", "position_size"}
        self.assertTrue(names.isdisjoint(forbidden))

    @patch("sys.argv", ["yatl", "strategy-contract-check"])
    def test_cli_reports_research_only_boundary(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P3 signal contract", text)
        self.assertIn("NO_TRADE/ENTER_LONG", text)
        self.assertIn("No sizing", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
